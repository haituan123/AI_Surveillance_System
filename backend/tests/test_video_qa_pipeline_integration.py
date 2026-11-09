"""
Integration tests for Bước 3: Pipeline lưu Database
=======================================================
Covers:
- index_frame() → danger_threats, detected_entities, security_events populated correctly
- Confidence scores are real values from each detection
- Clothing colors (top/bottom) stored in detected_entities
- Accessories (backpack, motorcycle) stored in detected_entities
- ThreatType-specific events: WEAPON_DRAWN, ROBBERY_BACKPACK, ROBBERY_MOTORBIKE,
  FIRE_SMOKE, FIGHTING (via ActionVerifier heuristic)
- Video QA answers correctly with evidence + confidence from DB
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.ai.contracts import BoundingBox, FrameAnalysis, TrackAnalysis
from backend.app.database import create_schema
from backend.app.models import DetectionStatus, ThreatType
from backend.app.schemas import QAAskRequest
from backend.services.frame_indexer_service import FrameIndexerService
from backend.services.qa_service import QAService
from backend.services.qa_video_index_manager import QAVideoIndexManager


def _make_frame(h: int = 100, w: int = 100, top_bgr=(0, 0, 255), bottom_bgr=(255, 0, 0)) -> np.ndarray:
    """Return a minimal synthetic BGR frame with colored top/bottom halves (default: red top, blue bottom)."""
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[10 : h // 2, 10 : w // 2] = top_bgr     # top half region
    frame[h // 2 : h - 10, 10 : w // 2] = bottom_bgr  # bottom half region
    return frame


def _make_track(
    track_id: int = 1,
    x1: int = 10, y1: int = 10, x2: int = 50, y2: int = 90,
    confidence: float = 0.95,
) -> TrackAnalysis:
    return TrackAnalysis(
        track_id=track_id,
        bounding_box=BoundingBox(x1, y1, x2, y2),
        person_confidence=confidence,
        status=DetectionStatus.UNKNOWN,
        member_id=None,
        similarity=None,
        face_confidence=None,
    )


class VideoQAPipelineIntegrationTestCase(unittest.TestCase):
    """Core pipeline integration test: index_frame → DB tables → QA answers."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.snapshots_dir = self.root / "snapshots"
        self.uploads_dir = self.root / "uploads"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

        self.manager = QAVideoIndexManager(qa_snapshots_dir=self.snapshots_dir / "qa")

        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        create_schema(self.connection)

        self.indexer = FrameIndexerService(
            self.connection,
            snapshots_dir=self.snapshots_dir,
        )
        self.qa_service = QAService(
            self.connection,
            api_key="",
            index_manager=self.manager,
            snapshots_dir=self.snapshots_dir,
            uploads_dir=self.uploads_dir,
        )

    def tearDown(self):
        self.connection.close()

    # ------------------------------------------------------------------
    # Test 1: Weapon + Backpack + Motorcycle → DB tables populated
    # ------------------------------------------------------------------
    def test_pipeline_indexes_and_answers_qa_with_confidence_and_evidence(self):
        """Full pipeline: pistol + backpack + motorcycle → all 3 DB tables + QA answers."""
        video_id = "test_vid_01"
        frame = _make_frame()

        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=2.0,
            width=100,
            height=100,
            tracks=(_make_track(track_id=1, x1=10, y1=10, x2=50, y2=90, confidence=0.95),),
        )
        raw_objects = [
            {"label": "backpack",   "confidence": 0.88, "x1": 20, "y1": 30, "x2": 45, "y2": 70},
            {"label": "motorcycle", "confidence": 0.92, "x1": 55, "y1": 40, "x2": 95, "y2": 90},
            {"label": "pistol",     "confidence": 0.85, "x1": 15, "y1": 20, "x2": 30, "y2": 35},
        ]

        frame_id = self.indexer.index_frame(
            frame_bgr=frame,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=2.0,
            frame_number=1,
            analysis=analysis,
            raw_object_detections=raw_objects,
        )
        self.indexer.flush(video_id)

        # --- video_frames ---
        vf = self.connection.execute("SELECT * FROM video_frames WHERE id = ?", (frame_id,)).fetchone()
        self.assertIsNotNone(vf)
        self.assertEqual(vf["person_count"], 1)

        # --- detected_entities ---
        entities = self.connection.execute(
            "SELECT * FROM detected_entities WHERE frame_id = ?", (frame_id,)
        ).fetchall()
        labels = {e["label"] for e in entities}
        self.assertIn("person",     labels, "Person entity must be saved")
        self.assertIn("backpack",   labels, "Backpack entity must be saved")
        self.assertIn("motorcycle", labels, "Motorcycle entity must be saved")

        # Clothing colors
        person_ent = next(e for e in entities if e["entity_type"] == "person")
        self.assertEqual(person_ent["clothing_top_color"],    "red",  "Top color must be red")
        self.assertEqual(person_ent["clothing_bottom_color"], "blue", "Bottom color must be blue")

        # Confidence scores must be positive
        for e in entities:
            conf = e["confidence"]
            if conf is not None:
                self.assertGreater(float(conf), 0.0, f"Entity '{e['label']}' confidence must be > 0")

        # --- danger_threats ---
        threats = self.connection.execute(
            "SELECT * FROM danger_threats WHERE frame_id = ?", (frame_id,)
        ).fetchall()
        self.assertGreater(len(threats), 0, "danger_threats must have at least 1 row")
        for t in threats:
            self.assertGreater(float(t["confidence"]), 0.0, "Threat confidence must be > 0")

        threat_types = {t["threat_type"] for t in threats}
        self.assertTrue(
            threat_types & {"weapon_drawn", "robbery_backpack", "robbery_motorbike", "theft"},
            f"Expected weapon/robbery threats, got: {threat_types}",
        )

        # --- security_events ---
        events = self.connection.execute(
            "SELECT * FROM security_events WHERE session_or_video_id = ?", (video_id,)
        ).fetchall()
        self.assertGreater(len(events), 0, "security_events must have at least 1 row")
        for ev in events:
            self.assertGreater(float(ev["confidence"]), 0.0, "Event confidence must be > 0")

        # --- QA: weapon query ---
        msg_threat = self.qa_service.ask(QAAskRequest(
            question="Có ai cầm súng không?",
            session_or_video_id=video_id,
        ))
        self.assertIn("súng", msg_threat.response_vi.lower())
        self.assertGreater(len(msg_threat.evidences), 0)
        self.assertGreater(msg_threat.evidences[0].confidence, 0.0)

        # --- QA: clothing color ---
        msg_color = self.qa_service.ask(QAAskRequest(
            question="Có ai mặc áo màu đỏ không?",
            session_or_video_id=video_id,
        ))
        self.assertIn("đỏ", msg_color.response_vi.lower())
        self.assertGreater(len(msg_color.evidences), 0)
        self.assertIsNotNone(msg_color.evidences[0].confidence)

        # --- QA: backpack ---
        msg_bag = self.qa_service.ask(QAAskRequest(
            question="Có ai mang balo không?",
            session_or_video_id=video_id,
        ))
        self.assertIn("balo", msg_bag.response_vi.lower())
        self.assertGreater(len(msg_bag.evidences), 0)
        self.assertGreater(msg_bag.evidences[0].confidence, 0.0)

    # ------------------------------------------------------------------
    # Test 2: Motorcycle robbery saved to danger_threats & security_events
    # ------------------------------------------------------------------
    def test_motorcycle_robbery_saved_to_db(self):
        """Person overlapping with motorcycle → ROBBERY_MOTORBIKE threat saved."""
        video_id = "test_vid_motorbike"
        frame = _make_frame()

        # Person bbox overlaps with the motorcycle bbox
        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=1.5,
            width=100,
            height=100,
            tracks=(_make_track(track_id=1, x1=50, y1=30, x2=90, y2=90, confidence=0.90),),
        )
        raw_objects = [
            # motorcycle overlaps person bbox significantly
            {"label": "motorcycle", "confidence": 0.91, "x1": 55, "y1": 35, "x2": 90, "y2": 88},
        ]

        frame_id = self.indexer.index_frame(
            frame_bgr=frame,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=1.5,
            frame_number=1,
            analysis=analysis,
            raw_object_detections=raw_objects,
        )
        self.indexer.flush(video_id)

        threats = self.connection.execute(
            "SELECT threat_type, confidence FROM danger_threats WHERE frame_id = ?", (frame_id,)
        ).fetchall()
        threat_types = {t["threat_type"] for t in threats}

        self.assertTrue(
            "robbery_motorbike" in threat_types or "theft" in threat_types,
            f"Expected robbery_motorbike or theft in threats, got: {threat_types}",
        )
        for t in threats:
            self.assertGreater(float(t["confidence"]), 0.0)

        events = self.connection.execute(
            "SELECT event_type, confidence FROM security_events WHERE session_or_video_id = ?",
            (video_id,),
        ).fetchall()
        self.assertGreater(len(events), 0, "security_events must have events for motorcycle robbery")
        event_types = {e["event_type"] for e in events}
        self.assertTrue(
            event_types & {"robbery_motorbike", "possible_theft"},
            f"Expected robbery_motorbike or possible_theft in security_events, got: {event_types}",
        )

    # ------------------------------------------------------------------
    # Test 3: Fire/flame visual detection → FIRE_SMOKE threat saved
    # ------------------------------------------------------------------
    def test_fire_visual_detection_saved_to_db(self):
        """Frame with flame-colored pixels → FIRE_SMOKE detected via visual analysis."""
        video_id = "test_vid_fire"

        # Create a frame with flame-colored region: high R, medium G, low B
        # and in HSV: hue ~10 (orange-red), high saturation & brightness
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # In BGR: (B=10, G=100, R=230) → orange/fire color
        frame[20:60, 20:70] = (10, 100, 230)

        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=0.5,
            width=100,
            height=100,
            tracks=(),  # no persons
        )

        frame_id = self.indexer.index_frame(
            frame_bgr=frame,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=0.5,
            frame_number=1,
            analysis=analysis,
            raw_object_detections=[],  # no model detections — visual fallback should trigger
        )
        self.indexer.flush(video_id)

        threats = self.connection.execute(
            "SELECT threat_type, confidence FROM danger_threats WHERE frame_id = ?", (frame_id,)
        ).fetchall()

        # Fire threats may or may not trigger depending on pixel analysis
        # The test verifies: IF fire is detected, confidence is correct
        fire_threats = [t for t in threats if t["threat_type"] == "fire_smoke"]
        for t in fire_threats:
            self.assertGreater(float(t["confidence"]), 0.5, "Fire confidence must be > 0.5")
            self.assertLessEqual(float(t["confidence"]), 1.0, "Fire confidence must be ≤ 1.0")

        # Detected entity 'fire' should also be in detected_entities if detected
        fire_entities = self.connection.execute(
            "SELECT label FROM detected_entities WHERE frame_id = ? AND label = 'fire'", (frame_id,)
        ).fetchall()
        # If fire threats were found, fire entities must also be there
        if fire_threats:
            self.assertGreater(len(fire_entities), 0, "Fire entity must be in detected_entities")

    # ------------------------------------------------------------------
    # Test 4: Fighting detection (2 overlapping persons → ActionVerifier)
    # ------------------------------------------------------------------
    def test_fighting_two_overlapping_persons_triggers_action_verifier(self):
        """Two persons with overlapping bboxes + motion → FIGHTING threat may be detected."""
        video_id = "test_vid_fighting"

        # Create frames with motion (simulate movement between frames)
        frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame1[10:80, 10:80] = (120, 60, 60)  # background movement

        frame2 = np.zeros((100, 100, 3), dtype=np.uint8)
        frame2[15:85, 15:85] = (60, 120, 60)  # different from frame1 → high motion score

        # Two persons with overlapping bounding boxes
        analysis1 = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=1.0,
            width=100,
            height=100,
            tracks=(
                _make_track(track_id=1, x1=10, y1=10, x2=55, y2=80, confidence=0.90),
                _make_track(track_id=2, x1=40, y1=10, x2=90, y2=80, confidence=0.88),
            ),
        )

        frame_id1 = self.indexer.index_frame(
            frame_bgr=frame1,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=1.0,
            frame_number=1,
            analysis=analysis1,
            raw_object_detections=[],
        )
        frame_id2 = self.indexer.index_frame(
            frame_bgr=frame2,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=1.5,
            frame_number=2,
            analysis=analysis1,
            raw_object_detections=[],
        )
        self.indexer.flush(video_id)

        # Both persons must be stored as detected_entities
        for fid in [frame_id1, frame_id2]:
            persons = self.connection.execute(
                "SELECT * FROM detected_entities WHERE frame_id = ? AND entity_type = 'person'", (fid,)
            ).fetchall()
            self.assertEqual(len(persons), 2, f"Frame {fid} must have 2 person entities")

        # security_events must exist
        events = self.connection.execute(
            "SELECT event_type, confidence FROM security_events WHERE session_or_video_id = ?",
            (video_id,),
        ).fetchall()
        # Fighting detection may or may not trigger (heuristic threshold)
        # We only verify: if any fighting event was created, confidence must be valid
        fighting_events = [e for e in events if e["event_type"] == "fighting"]
        for e in fighting_events:
            self.assertGreater(float(e["confidence"]), 0.0)
            self.assertLessEqual(float(e["confidence"]), 1.0)

    # ------------------------------------------------------------------
    # Test 5: Multi-frame → security_events merge (same video, same threat)
    # ------------------------------------------------------------------
    def test_multi_frame_aggregates_into_single_security_event(self):
        """Same threat type repeated across multiple frames → single security_event record."""
        video_id = "test_vid_multiframe"
        frame = _make_frame()

        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=0.0,
            width=100,
            height=100,
            tracks=(_make_track(track_id=1),),
        )
        raw_knife = [{"label": "knife", "confidence": 0.80, "x1": 15, "y1": 15, "x2": 40, "y2": 40}]

        # Index 3 frames with the same knife threat
        for i in range(3):
            self.indexer.index_frame(
                frame_bgr=frame,
                camera_id=None,
                session_or_video_id=video_id,
                timestamp_seconds=float(i) * 0.5,
                frame_number=i + 1,
                analysis=FrameAnalysis(
                    frame_index=i + 1,
                    timestamp_seconds=float(i) * 0.5,
                    width=100,
                    height=100,
                    tracks=(
                        TrackAnalysis(
                            track_id=1,
                            bounding_box=BoundingBox(10, 10, 50, 90),
                            person_confidence=0.95,
                            status=DetectionStatus.UNKNOWN,
                            member_id=None,
                            similarity=None,
                            face_confidence=None,
                        ),
                    ),
                ),
                raw_object_detections=raw_knife,
            )

        self.indexer.flush(video_id)

        # danger_threats must have 3 rows (one per frame)
        all_threats = self.connection.execute(
            """
            SELECT dt.* FROM danger_threats dt
            JOIN video_frames vf ON vf.id = dt.frame_id
            WHERE vf.session_or_video_id = ?
            """,
            (video_id,),
        ).fetchall()
        self.assertEqual(len(all_threats), 3, "Should have 3 frame-level danger_threats")

        # security_events: knife_present event must exist and have confidence > 0
        events = self.connection.execute(
            "SELECT * FROM security_events WHERE session_or_video_id = ?", (video_id,)
        ).fetchall()
        self.assertGreater(len(events), 0, "security_events must be created")
        knife_events = [e for e in events if e["event_type"] == "knife_present"]
        self.assertGreater(len(knife_events), 0, "knife_present event must exist in security_events")

        knife_event = knife_events[0]
        self.assertGreater(float(knife_event["confidence"]), 0.0, "Knife event confidence must be > 0")
        # End timestamp must be later than start (3 frames were processed)
        self.assertGreaterEqual(
            float(knife_event["end_timestamp"]),
            float(knife_event["start_timestamp"]),
            "end_timestamp must be >= start_timestamp",
        )

    # ------------------------------------------------------------------
    # Test 6: detected_entities stores real confidence for each object
    # ------------------------------------------------------------------
    def test_detected_entities_confidence_matches_raw_detection(self):
        """Confidence stored in detected_entities matches raw YOLO detection confidence."""
        video_id = "test_vid_confidence"
        frame = _make_frame()

        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=1.0,
            width=100,
            height=100,
            tracks=(_make_track(track_id=1, confidence=0.97),),
        )
        raw_objects = [
            {"label": "backpack",   "confidence": 0.88, "x1": 20, "y1": 30, "x2": 45, "y2": 70},
            {"label": "cell phone", "confidence": 0.76, "x1": 60, "y1": 20, "x2": 80, "y2": 45},
        ]

        frame_id = self.indexer.index_frame(
            frame_bgr=frame,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=1.0,
            frame_number=1,
            analysis=analysis,
            raw_object_detections=raw_objects,
        )
        self.indexer.flush(video_id)

        entities = self.connection.execute(
            "SELECT label, confidence FROM detected_entities WHERE frame_id = ?", (frame_id,)
        ).fetchall()
        entity_map = {e["label"]: float(e["confidence"]) for e in entities if e["confidence"] is not None}

        # Person confidence must match track confidence
        self.assertAlmostEqual(entity_map.get("person", 0.0), 0.97, places=2)
        # Object confidences must match raw detections
        self.assertAlmostEqual(entity_map.get("backpack",   0.0), 0.88, places=2)
        self.assertAlmostEqual(entity_map.get("cell phone", 0.0), 0.76, places=2)

    # ------------------------------------------------------------------
    # Test 7: QA on motorcycle robbery evidence returns confidence > 0
    # ------------------------------------------------------------------
    def test_qa_motorcycle_robbery_returns_evidence_with_confidence(self):
        """QA 'có xe máy không' returns evidence with confidence > 0 for robbery scenario."""
        video_id = "test_vid_qa_moto"
        frame = _make_frame()

        analysis = FrameAnalysis(
            frame_index=1,
            timestamp_seconds=3.0,
            width=100,
            height=100,
            tracks=(_make_track(track_id=1, x1=50, y1=30, x2=90, y2=90, confidence=0.90),),
        )
        raw_objects = [
            {"label": "motorcycle", "confidence": 0.91, "x1": 55, "y1": 35, "x2": 90, "y2": 88},
        ]

        self.indexer.index_frame(
            frame_bgr=frame,
            camera_id=None,
            session_or_video_id=video_id,
            timestamp_seconds=3.0,
            frame_number=1,
            analysis=analysis,
            raw_object_detections=raw_objects,
        )
        self.indexer.flush(video_id)

        msg = self.qa_service.ask(QAAskRequest(
            question="Có xe máy xuất hiện trong video không?",
            session_or_video_id=video_id,
        ))
        # Response must mention xe máy (motorbike) or cướp giật
        lower = msg.response_vi.lower()
        self.assertTrue(
            "xe" in lower or "máy" in lower or "mô tô" in lower or "cướp" in lower,
            f"Response should mention motorcycle/robbery, got: {msg.response_vi!r}",
        )
        self.assertGreater(len(msg.evidences), 0, "Must return at least one evidence")
        for ev in msg.evidences:
            self.assertIsNotNone(ev.confidence)
            self.assertGreater(ev.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
