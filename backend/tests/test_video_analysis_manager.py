import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from backend.ai.contracts import (
    BoundingBox,
    FrameAnalysis,
    TrackAnalysis,
)
from backend.app.database import create_schema
from backend.app.models import DetectionStatus, VideoAnalysisState
from backend.services.gallery_service import AnalysisRuntime
from backend.services.video_analysis_manager import (
    VideoAnalysisBusyError,
    VideoAnalysisManager,
    VideoAnalysisNotFoundError,
)


class FakeVideoEngine:
    def __init__(self, status=DetectionStatus.UNKNOWN):
        self.status = status
        self.reset_called = False
        self.person_tracker = None

    def analyze_frame(self, frame, *, frame_index, timestamp_seconds):
        return FrameAnalysis(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            width=frame.shape[1],
            height=frame.shape[0],
            tracks=(
                TrackAnalysis(
                    track_id=1,
                    bounding_box=BoundingBox(1, 1, 12, 14),
                    person_confidence=0.9,
                    status=self.status,
                    member_id=None,
                    similarity=0.2,
                    face_confidence=0.9,
                ),
            ),
        )

    def reset(self):
        self.reset_called = True


class FiniteVideoCapture:
    def __init__(self, path, *, frames=6, opened=True, delay=0.0):
        self.path = path
        self.frames_remaining = frames
        self.total_frames = frames
        self.opened = opened
        self.delay = delay
        self.released = False

    def isOpened(self):
        return self.opened

    def get(self, property_id):
        import cv2

        if property_id == cv2.CAP_PROP_FPS:
            return 25.0
        if property_id == cv2.CAP_PROP_FRAME_COUNT:
            return float(self.total_frames)
        return 0.0

    def read(self):
        if self.delay:
            time.sleep(self.delay)
        if not self.opened or self.frames_remaining <= 0:
            return False, None
        self.frames_remaining -= 1
        return True, np.zeros((20, 30, 3), dtype=np.uint8)

    def release(self):
        self.released = True


class VideoAnalysisManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "app.db"
        connection = self.connection_factory()
        create_schema(connection)
        connection.close()
        self.engine = FakeVideoEngine()
        self.captures = []

    def connection_factory(self):
        connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def make_input(self, name="video.mp4"):
        path = self.root / name
        path.write_bytes(b"temporary video")
        return path

    def make_manager(self, *, capture_factory=None):
        if capture_factory is None:
            def capture_factory(path):
                capture = FiniteVideoCapture(path)
                self.captures.append(capture)
                return capture

        manager = VideoAnalysisManager(
            connection_factory=self.connection_factory,
            capture_factory=capture_factory,
            runtime_factory=lambda connection: AnalysisRuntime(
                engine=self.engine,
                member_names={},
            ),
            result_ttl_seconds=60,
            stop_timeout_seconds=1,
        )
        self.addCleanup(manager.shutdown)
        return manager

    def wait_for_terminal(self, manager, job_id, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = manager.status(job_id)
            if status["state"] in {
                VideoAnalysisState.COMPLETED,
                VideoAnalysisState.FAILED,
                VideoAnalysisState.CANCELLED,
            }:
                return status
            time.sleep(0.005)
        self.fail("Timed out waiting for video analysis")

    def test_completed_job_is_temporary_and_does_not_touch_database(self):
        manager = self.make_manager()
        input_path = self.make_input()

        submitted = manager.submit(input_path, "video.mp4")
        status = self.wait_for_terminal(manager, submitted["job_id"])
        results = manager.results(submitted["job_id"])
        frame = manager.latest_frame(submitted["job_id"])

        self.assertEqual(status["state"], VideoAnalysisState.COMPLETED)
        self.assertFalse(status["persistent"])
        self.assertEqual(status["processed_frames"], 6)
        self.assertEqual(status["progress"], 1.0)
        self.assertFalse(input_path.exists())
        self.assertTrue(self.engine.reset_called)
        self.assertTrue(self.captures[0].released)
        self.assertTrue(frame.startswith(b"\xff\xd8"))
        self.assertEqual(results["summary"]["unknown_events"], 1)
        self.assertEqual(results["summary"]["total_frames"], 6)
        self.assertFalse(results["persistent"])

        connection = self.connection_factory()
        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in (
                "surveillance_sessions",
                "detection_logs",
                "alerts",
            )
        }
        connection.close()
        self.assertEqual(
            counts,
            {
                "surveillance_sessions": 0,
                "detection_logs": 0,
                "alerts": 0,
            },
        )

    def test_knife_event_exposes_temporary_evidence_snapshot(self):
        class FakeObjectDetector:
            @staticmethod
            def detect_objects(frame):
                return [
                    {
                        "label": "knife",
                        "confidence": 0.91,
                        "x1": 2,
                        "y1": 3,
                        "x2": 8,
                        "y2": 12,
                    }
                ]

        self.engine.person_tracker = FakeObjectDetector()
        manager = self.make_manager()
        submitted = manager.submit(self.make_input(), "knife.mp4")
        self.wait_for_terminal(manager, submitted["job_id"])

        results = manager.results(submitted["job_id"])
        threats = [event for event in results["events"] if event["is_threat"]]

        self.assertEqual(results["summary"]["threat_events"], 1)
        self.assertEqual(len(threats), 1)
        self.assertEqual(threats[0]["event_type"], "knife_threat")
        self.assertEqual(threats[0]["confidence"], 0.91)
        self.assertEqual(threats[0]["bounding_box"], [2, 3, 8, 12])
        self.assertTrue(threats[0]["snapshot_url"])
        snapshot = manager.event_snapshot(
            submitted["job_id"],
            threats[0]["event_id"],
        )
        self.assertTrue(snapshot.startswith(b"\xff\xd8"))

    def test_failed_job_deletes_input(self):
        captures = []

        def capture_factory(path):
            capture = FiniteVideoCapture(path, opened=False)
            captures.append(capture)
            return capture

        manager = self.make_manager(capture_factory=capture_factory)
        input_path = self.make_input()
        submitted = manager.submit(input_path, "video.mp4")

        failed = self.wait_for_terminal(manager, submitted["job_id"])

        self.assertEqual(failed["state"], VideoAnalysisState.FAILED)
        self.assertIn("Could not open uploaded video", failed["error_message"])
        self.assertFalse(input_path.exists())
        self.assertTrue(captures[0].released)

    def test_only_one_job_can_run_and_delete_cancels_it(self):
        def capture_factory(path):
            return FiniteVideoCapture(path, frames=1000, delay=0.002)

        manager = self.make_manager(capture_factory=capture_factory)
        first_path = self.make_input("first.mp4")
        second_path = self.make_input("second.mp4")
        first = manager.submit(first_path, "first.mp4")

        with self.assertRaises(VideoAnalysisBusyError):
            manager.submit(second_path, "second.mp4")

        manager.delete(first["job_id"])

        self.assertFalse(first_path.exists())
        with self.assertRaises(VideoAnalysisNotFoundError):
            manager.status(first["job_id"])
        second_path.unlink()


if __name__ == "__main__":
    unittest.main()
