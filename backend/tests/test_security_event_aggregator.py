import json
import sqlite3
import unittest

from backend.ai.contracts import BoundingBox, FrameAnalysis, TrackAnalysis
from backend.app.database import create_schema
from backend.app.models import DetectionStatus
from backend.services.security_event_aggregator import SecurityEventAggregator


def make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    create_schema(connection)
    return connection


class SecurityEventAggregatorTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_connection()
        self.aggregator = SecurityEventAggregator(
            self.connection,
            session_or_video_id="video-1",
            min_confirmations=2,
            max_gap_seconds=1.0,
            model_version="test-rule-v1",
        )
        self.analysis = FrameAnalysis(
            frame_index=0,
            timestamp_seconds=0.0,
            width=640,
            height=480,
            tracks=(
                TrackAnalysis(
                    track_id=7,
                    bounding_box=BoundingBox(10, 10, 150, 300),
                    person_confidence=0.95,
                    status=DetectionStatus.UNKNOWN,
                    member_id=None,
                    similarity=None,
                    face_confidence=None,
                ),
            ),
        )

    def tearDown(self):
        self.connection.close()

    def _add_frame(
        self,
        timestamp: float,
        *,
        threat_type: str | None = None,
        confidence: float = 0.8,
        description: str = "",
    ) -> int:
        frame = self.connection.execute(
            """
            INSERT INTO video_frames (
                session_or_video_id, timestamp_seconds, frame_number,
                frame_path, person_count
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "video-1",
                timestamp,
                round(timestamp * 100),
                f"snapshots/frame_{timestamp:.3f}.jpg",
                1,
            ),
        )
        frame_id = int(frame.lastrowid)
        if threat_type is not None:
            self.connection.execute(
                """
                INSERT INTO danger_threats (
                    frame_id, threat_type, confidence, snapshot_path,
                    description_en, bbox_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    frame_id,
                    threat_type,
                    confidence,
                    f"snapshots/frame_{timestamp:.3f}.jpg",
                    description,
                    json.dumps([20, 20, 80, 120]),
                ),
            )
        self.connection.commit()
        return frame_id

    def _process(self, frame_id: int, timestamp: float) -> None:
        self.aggregator.process_frame(
            frame_id=frame_id,
            timestamp_seconds=timestamp,
            analysis=self.analysis,
        )

    def test_confirms_merges_and_closes_one_event(self):
        first = self._add_frame(
            0.0,
            threat_type="knife_threat",
            confidence=0.65,
            description="Person detected holding a knife",
        )
        self._process(first, 0.0)
        count = self.connection.execute(
            "SELECT COUNT(*) FROM security_events"
        ).fetchone()[0]
        self.assertEqual(count, 0)

        best = self._add_frame(
            0.125,
            threat_type="knife_threat",
            confidence=0.93,
            description="Person detected holding a knife",
        )
        self._process(best, 0.125)
        third = self._add_frame(
            0.25,
            threat_type="knife_threat",
            confidence=0.75,
            description="Person detected holding a knife",
        )
        self._process(third, 0.25)

        row = self.connection.execute(
            "SELECT * FROM security_events"
        ).fetchone()
        self.assertEqual(row["event_type"], "knife_present")
        self.assertEqual(row["start_timestamp"], 0.0)
        self.assertEqual(row["end_timestamp"], 0.25)
        self.assertAlmostEqual(row["confidence"], 0.93)
        self.assertEqual(row["primary_frame_id"], best)
        self.assertEqual(json.loads(row["actor_track_ids_json"]), [7])
        self.assertEqual(json.loads(row["object_labels_json"]), ["knife"])
        self.assertEqual(row["status"], "open")

        empty = self._add_frame(1.5)
        self._process(empty, 1.5)
        closed = self.connection.execute(
            "SELECT * FROM security_events"
        ).fetchone()
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["end_timestamp"], 0.25)

    def test_separate_incidents_do_not_create_frame_duplicates(self):
        for timestamp in (0.0, 0.125, 0.25):
            frame_id = self._add_frame(
                timestamp,
                threat_type="fire_smoke",
                description="Fire hazard detected",
            )
            self._process(frame_id, timestamp)

        empty = self._add_frame(1.5)
        self._process(empty, 1.5)

        for timestamp in (2.0, 2.125):
            frame_id = self._add_frame(
                timestamp,
                threat_type="fire_smoke",
                description="Fire hazard detected",
            )
            self._process(frame_id, timestamp)
        self.aggregator.flush()

        rows = self.connection.execute(
            "SELECT status FROM security_events ORDER BY id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["status"] == "closed" for row in rows))

    def test_single_frame_false_positive_is_not_persisted(self):
        frame_id = self._add_frame(
            0.0,
            threat_type="weapon_drawn",
            description="Firearm detected",
        )
        self._process(frame_id, 0.0)
        self.aggregator.flush()

        count = self.connection.execute(
            "SELECT COUNT(*) FROM security_events"
        ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
