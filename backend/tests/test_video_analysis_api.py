import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.models import LiveSurveillanceState, VideoAnalysisState
from backend.main import create_app
from backend.routes.surveillance_routes import get_surveillance_manager
from backend.routes.video_analysis_routes import get_video_analysis_manager
from backend.services.surveillance_manager import SurveillanceStatusSnapshot
from backend.services.video_analysis_manager import (
    VideoAnalysisBusyError,
    VideoAnalysisNotFoundError,
)


class FakeLiveManager:
    def __init__(self):
        self.running = False

    def status(self):
        return SurveillanceStatusSnapshot(
            state=(
                LiveSurveillanceState.RUNNING
                if self.running
                else LiveSurveillanceState.IDLE
            ),
            running=self.running,
            camera_id=1 if self.running else None,
            session_id=1 if self.running else None,
            frames_processed=0,
            fps=0.0,
            started_at=None,
            error_message=None,
        )


class FakeVideoManager:
    def __init__(self):
        self.raise_busy = False
        self.submitted_path = None
        self.deleted_job_id = None
        self.frame = b"\xff\xd8temporary-frame\xff\xd9"

    def submit(self, path, filename):
        if self.raise_busy:
            raise VideoAnalysisBusyError("Video analysis is busy")
        self.submitted_path = path
        return self.status("job-1")

    def status(self, job_id):
        if job_id == "missing":
            raise VideoAnalysisNotFoundError("Video-analysis job not found")
        return {
            "job_id": job_id,
            "filename": "video.mp4",
            "state": VideoAnalysisState.RUNNING,
            "persistent": False,
            "processed_frames": 2,
            "total_frames": 10,
            "progress": 0.2,
            "processing_fps": 8.0,
            "created_at": "2026-07-28T10:00:00+00:00",
            "completed_at": None,
            "error_message": None,
        }

    def results(self, job_id):
        if job_id == "missing":
            raise VideoAnalysisNotFoundError("Video-analysis job not found")
        return {
            "job_id": job_id,
            "filename": "video.mp4",
            "state": VideoAnalysisState.RUNNING,
            "persistent": False,
            "summary": {
                "total_frames": 2,
                "duration_seconds": 0.08,
                "average_processing_fps": 8.0,
                "known_events": 0,
                "unknown_events": 0,
                "events_truncated": False,
            },
            "events": [],
            "error_message": None,
        }

    def latest_frame(self, job_id):
        if job_id == "missing":
            raise VideoAnalysisNotFoundError("Video-analysis job not found")
        return self.frame

    def event_snapshot(self, job_id, event_id):
        if job_id == "missing":
            raise VideoAnalysisNotFoundError("Video-analysis job not found")
        if event_id == "missing":
            return None
        return self.frame

    def delete(self, job_id):
        if job_id == "missing":
            raise VideoAnalysisNotFoundError("Video-analysis job not found")
        self.deleted_job_id = job_id


class VideoAnalysisApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.upload_directory = Path(self.temporary_directory.name)
        self.video_manager = FakeVideoManager()
        self.live_manager = FakeLiveManager()
        self.app = create_app(initialize_database=False)
        self.app.dependency_overrides[get_video_analysis_manager] = (
            lambda: self.video_manager
        )
        self.app.dependency_overrides[get_surveillance_manager] = (
            lambda: self.live_manager
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()
        self.client.close()

    def submit(self, filename="video.mp4", content=b"video"):
        with patch(
            "backend.routes.video_analysis_routes.TEMP_UPLOADS_DIR",
            self.upload_directory,
        ):
            return self.client.post(
                "/video-analysis",
                files={"file": (filename, content, "video/mp4")},
            )

    def test_submit_marks_job_non_persistent(self):
        response = self.submit()

        self.assertEqual(response.status_code, 202)
        self.assertFalse(response.json()["persistent"])
        self.assertEqual(response.json()["state"], "running")
        self.assertTrue(self.video_manager.submitted_path.exists())
        self.video_manager.submitted_path.unlink()

    def test_unsupported_empty_and_oversized_uploads_are_rejected(self):
        self.assertEqual(self.submit("video.txt").status_code, 400)
        self.assertEqual(self.submit(content=b"").status_code, 400)
        with patch(
            "backend.routes.video_analysis_routes.VIDEO_UPLOAD_MAX_BYTES",
            3,
        ):
            oversized = self.submit(content=b"1234")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(list(self.upload_directory.iterdir()), [])

    def test_live_surveillance_blocks_upload_before_file_is_saved(self):
        self.live_manager.running = True

        response = self.submit()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(list(self.upload_directory.iterdir()), [])

    def test_busy_manager_removes_new_temporary_file(self):
        self.video_manager.raise_busy = True

        response = self.submit()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(list(self.upload_directory.iterdir()), [])

    def test_status_results_frame_and_delete(self):
        status = self.client.get("/video-analysis/job-1/status")
        results = self.client.get("/video-analysis/job-1/results")
        frame = self.client.get("/video-analysis/job-1/frame")
        event_frame = self.client.get(
            "/video-analysis/job-1/events/event-1/snapshot"
        )
        deleted = self.client.delete("/video-analysis/job-1")

        self.assertEqual(status.status_code, 200)
        self.assertFalse(results.json()["persistent"])
        self.assertEqual(frame.headers["content-type"], "image/jpeg")
        self.assertEqual(frame.headers["cache-control"], "no-store")
        self.assertEqual(event_frame.status_code, 200)
        self.assertEqual(event_frame.headers["content-type"], "image/jpeg")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.video_manager.deleted_job_id, "job-1")

    def test_missing_job_returns_404(self):
        self.assertEqual(
            self.client.get("/video-analysis/missing/status").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                "/video-analysis/job-1/events/missing/snapshot"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete("/video-analysis/missing").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
