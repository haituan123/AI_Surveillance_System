import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.ai.attribute_extractor import AttributeExtractor, ColorAnalyzer
from backend.ai.contracts import BoundingBox, FrameAnalysis, TrackAnalysis
from backend.ai.threat_detector import ThreatAndObjectDetector
from backend.app.database import create_schema
from backend.app.config import resolve_storage_path
from backend.app.models import DetectionStatus, ThreatType
from backend.services.frame_indexer_service import FrameIndexerService


def make_test_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


class AttributeExtractorTestCase(unittest.TestCase):
    def test_extract_red_top_blue_bottom(self):
        # Create a synthetic image: top half red (BGR: 0, 0, 255), bottom half blue (BGR: 255, 0, 0)
        img = np.zeros((100, 50, 3), dtype=np.uint8)
        img[0:50, :] = (0, 0, 255)  # Red in BGR
        img[50:100, :] = (255, 0, 0)  # Blue in BGR

        top_color, bottom_color = ColorAnalyzer.extract_clothing_colors(img)
        self.assertEqual(top_color, "red")
        self.assertEqual(bottom_color, "blue")

    def test_extract_pink_purple_brown(self):
        # Hot Pink in BGR: (180, 105, 255)
        img_pink = np.full((60, 40, 3), (180, 105, 255), dtype=np.uint8)
        self.assertEqual(ColorAnalyzer.get_dominant_color(img_pink), "pink")

        # Purple in BGR: (180, 50, 130)
        img_purple = np.full((60, 40, 3), (180, 50, 130), dtype=np.uint8)
        self.assertEqual(ColorAnalyzer.get_dominant_color(img_purple), "purple")

        # Brown in BGR: (30, 60, 110)
        img_brown = np.full((60, 40, 3), (30, 60, 110), dtype=np.uint8)
        self.assertEqual(ColorAnalyzer.get_dominant_color(img_brown), "brown")

    def test_movement_direction_and_speed(self):
        extractor = AttributeExtractor()
        frame = np.zeros((200, 200, 3), dtype=np.uint8)

        # Frame 1: center at (50, 50) at t=0.0
        p1 = extractor.analyze_person(frame, track_id=1, x1=40, y1=40, x2=60, y2=60, timestamp_seconds=0.0)
        self.assertEqual(p1.movement_direction, "standing")

        # Frame 2: moved to right (100, 50) at t=0.5s -> moving left_to_right
        p2 = extractor.analyze_person(frame, track_id=1, x1=90, y1=40, x2=110, y2=60, timestamp_seconds=0.5)
        self.assertEqual(p2.movement_direction, "left_to_right")
        self.assertGreater(p2.speed_px_per_sec, 50.0)


class ThreatDetectorTestCase(unittest.TestCase):
    def test_detect_knife_threat(self):
        detector = ThreatAndObjectDetector()
        raw_dets = [
            {"label": "knife", "confidence": 0.88, "x1": 50, "y1": 50, "x2": 80, "y2": 80},
            {"label": "backpack", "confidence": 0.90, "x1": 100, "y1": 100, "x2": 150, "y2": 150},
        ]
        person_boxes = [BoundingBox(x1=90, y1=90, x2=160, y2=180)]

        objects, threats = detector.evaluate_detections(raw_dets, person_boxes=person_boxes)
        self.assertEqual(len(objects), 2)
        threat_types = [t.threat_type for t in threats]
        self.assertIn(ThreatType.KNIFE_THREAT, threat_types)
        self.assertIn(ThreatType.THEFT, threat_types)

    def test_detect_hat_and_food_items(self):
        detector = ThreatAndObjectDetector()
        raw_dets = [
            {"label": "hat", "confidence": 0.85, "x1": 10, "y1": 10, "x2": 40, "y2": 40},
            {"label": "pizza", "confidence": 0.92, "x1": 60, "y1": 60, "x2": 90, "y2": 90},
            {"label": "cup", "confidence": 0.78, "x1": 110, "y1": 110, "x2": 130, "y2": 130},
        ]
        objects, threats = detector.evaluate_detections(raw_dets)
        self.assertEqual(len(objects), 3)
        labels = [o.label for o in objects]
        self.assertIn("hat", labels)
        self.assertIn("pizza", labels)
        self.assertIn("cup", labels)


class FrameIndexerServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_test_connection()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.service = FrameIndexerService(
            self.connection,
            snapshots_dir=Path(self.tmp_dir.name) / "snapshots",
        )

        cam = self.connection.execute(
            "INSERT INTO cameras (name, source) VALUES (?, ?)",
            ("Main Camera", "0"),
        )
        self.camera_id = int(cam.lastrowid)

    def tearDown(self):
        self.connection.close()

    def test_index_frame_saves_entities_and_threats(self):
        self.assertFalse(self.service.snapshots_dir.exists())
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=12.5,
            width=100,
            height=100,
            tracks=(
                TrackAnalysis(
                    track_id=1,
                    bounding_box=BoundingBox(10, 10, 50, 90),
                    person_confidence=0.95,
                    status=DetectionStatus.KNOWN,
                    member_id=None,
                    similarity=0.85,
                    face_confidence=0.90,
                ),
            ),
        )
        raw_objects = [
            {"label": "knife", "confidence": 0.85, "x1": 20, "y1": 30, "x2": 40, "y2": 50}
        ]

        frame_id = self.service.index_frame(
            frame_bgr=frame,
            camera_id=self.camera_id,
            session_or_video_id="session_01",
            timestamp_seconds=12.5,
            frame_number=1,
            analysis=analysis,
            raw_object_detections=raw_objects,
            scene_caption_en="A person holding a knife near the entrance",
        )

        self.assertGreater(frame_id, 0)

        # Check video_frames
        vf = self.connection.execute("SELECT * FROM video_frames WHERE id = ?", (frame_id,)).fetchone()
        self.assertEqual(vf["person_count"], 1)
        self.assertEqual(vf["scene_caption_en"], "A person holding a knife near the entrance")
        self.assertEqual(resolve_storage_path(vf["frame_path"]).parent, self.service.snapshots_dir)
        self.assertTrue(resolve_storage_path(vf["frame_path"]).is_file())

        # Check detected_entities
        entities = self.connection.execute("SELECT * FROM detected_entities WHERE frame_id = ?", (frame_id,)).fetchall()
        self.assertEqual(len(entities), 2)  # 1 person + 1 knife

        # Check danger_threats
        threats = self.connection.execute("SELECT * FROM danger_threats WHERE frame_id = ?", (frame_id,)).fetchall()
        self.assertEqual(len(threats), 1)
        self.assertEqual(threats[0]["threat_type"], "knife_threat")
        self.assertEqual(threats[0]["snapshot_path"], vf["frame_path"])

    def test_frame_without_image_does_not_create_snapshot_directory(self):
        self.assertFalse(self.service.snapshots_dir.exists())
        analysis = FrameAnalysis(frame_index=0, timestamp_seconds=0, width=20, height=20, tracks=())
        frame_id = self.service.index_frame(
            np.zeros((20, 20, 3), dtype=np.uint8), camera_id=self.camera_id,
            session_or_video_id="empty", timestamp_seconds=0, frame_number=0, analysis=analysis,
        )
        self.assertFalse(self.service.snapshots_dir.exists())
        self.assertEqual(self.connection.execute("SELECT frame_path FROM video_frames WHERE id = ?", (frame_id,)).fetchone()[0], "")


if __name__ == "__main__":
    unittest.main()
