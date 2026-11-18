import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.database import create_schema
from backend.main import create_app
from backend.routes.alert_routes import get_alert_service
from backend.routes.log_routes import get_log_service
from backend.services.alert_service import AlertService
from backend.services.log_service import LogService


def make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    create_schema(connection)
    return connection


class LogAlertApiTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_connection()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.snapshots_dir = Path(self.temporary_directory.name)
        self.snapshot_path = self.snapshots_dir / "alert.jpg"
        self.snapshot_path.write_bytes(b"\xff\xd8test-jpeg\xff\xd9")

        camera = self.connection.execute(
            "INSERT INTO cameras (name, source) VALUES (?, ?)",
            ("Laptop Webcam", "0"),
        )
        session = self.connection.execute(
            """
            INSERT INTO surveillance_sessions (camera_id)
            VALUES (?)
            """,
            (camera.lastrowid,),
        )
        member = self.connection.execute(
            "INSERT INTO people (name) VALUES (?)",
            ("Known Member",),
        )
        known_log = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                member_id,
                track_id,
                status,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session.lastrowid,
                camera.lastrowid,
                member.lastrowid,
                1,
                "known",
                0.78,
            ),
        )
        unknown_log = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                track_id,
                status,
                confidence,
                snapshot_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session.lastrowid,
                camera.lastrowid,
                2,
                "unknown",
                0.20,
                str(self.snapshot_path),
            ),
        )
        alert = self.connection.execute(
            """
            INSERT INTO alerts (
                session_id,
                camera_id,
                detection_log_id,
                alert_type,
                message,
                confidence,
                snapshot_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.lastrowid,
                camera.lastrowid,
                unknown_log.lastrowid,
                "unknown_person",
                "Unknown person detected",
                0.20,
                str(self.snapshot_path),
            ),
        )
        self.connection.commit()
        self.camera_id = int(camera.lastrowid)
        self.known_log_id = int(known_log.lastrowid)
        self.unknown_log_id = int(unknown_log.lastrowid)
        self.alert_id = int(alert.lastrowid)

        self.app = create_app(initialize_database=False)
        self.app.dependency_overrides[get_log_service] = lambda: LogService(
            self.connection
        )
        self.app.dependency_overrides[get_alert_service] = (
            lambda: AlertService(self.connection)
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()
        self.client.close()
        self.connection.close()

    def test_log_listing_filter_and_latest(self):
        all_logs = self.client.get("/logs")
        known_logs = self.client.get("/logs?status=known")
        latest = self.client.get("/logs/latest")

        self.assertEqual(all_logs.status_code, 200)
        self.assertEqual(len(all_logs.json()), 2)
        self.assertEqual(len(known_logs.json()), 1)
        self.assertEqual(known_logs.json()[0]["member_name"], "Known Member")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["status"], "unknown")

    def test_security_events_are_exposed_with_video_and_evidence_metadata(self):
        conversation = self.connection.execute(
            "INSERT INTO qa_conversations (title) VALUES (?)",
            ("Incident review",),
        )
        self.connection.execute(
            """
            INSERT INTO qa_uploaded_videos (
                conversation_id, video_id, filename, file_path, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (conversation.lastrowid, "qa-fight", "fight.mp4", "fight.mp4", "completed"),
        )
        self.connection.execute(
            """
            INSERT INTO security_events (
                session_or_video_id, event_type, start_timestamp,
                end_timestamp, confidence, actor_track_ids_json,
                object_labels_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("qa-fight", "fighting", 2.5, 4.0, 0.87, "[3, 8]", '["person"]'),
        )
        self.connection.commit()

        response = self.client.get("/logs/security-events?event_type=fighting")

        self.assertEqual(response.status_code, 200)
        event = response.json()[0]
        self.assertEqual(event["source_type"], "qa_video")
        self.assertEqual(event["source_name"], "fight.mp4")
        self.assertEqual(event["detected_label"], "person")
        self.assertEqual(event["actor_track_ids"], [3, 8])
        self.assertAlmostEqual(event["confidence"], 0.87)

    def test_alert_listing_detail_latest_and_read_update(self):
        alerts = self.client.get("/alerts?is_read=false")
        latest = self.client.get("/alerts/latest")
        detail = self.client.get(f"/alerts/{self.alert_id}")
        updated = self.client.patch(
            f"/alerts/{self.alert_id}/read",
            json={"is_read": True},
        )

        self.assertEqual(len(alerts.json()), 1)
        self.assertEqual(latest.json()["id"], self.alert_id)
        self.assertEqual(
            detail.json()["snapshot_url"],
            f"/alerts/{self.alert_id}/snapshot",
        )
        self.assertTrue(updated.json()["is_read"])
        self.assertEqual(
            self.client.get("/alerts?is_read=false").json(),
            [],
        )

    def test_alert_snapshot_is_contained_and_non_cached(self):
        with patch(
            "backend.routes.alert_routes.SNAPSHOTS_DIR",
            self.snapshots_dir,
        ):
            response = self.client.get(
                f"/alerts/{self.alert_id}/snapshot"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, self.snapshot_path.read_bytes())

    def test_snapshot_outside_configured_directory_is_rejected(self):
        different_directory = self.snapshots_dir / "allowed"
        different_directory.mkdir()
        with patch(
            "backend.routes.alert_routes.SNAPSHOTS_DIR",
            different_directory,
        ):
            response = self.client.get(
                f"/alerts/{self.alert_id}/snapshot"
            )

        self.assertEqual(response.status_code, 404)

    def test_missing_records_return_404(self):
        self.assertEqual(self.client.get("/alerts/999").status_code, 404)
        self.assertEqual(self.client.delete("/logs/999").status_code, 404)
        self.assertEqual(self.client.delete("/alerts/999").status_code, 404)
        self.assertEqual(
            self.client.patch(
                "/alerts/999/read",
                json={"is_read": True},
            ).status_code,
            404,
        )

    def test_delete_log_removes_row_and_preserves_alert_snapshot(self):
        response = self.client.delete(f"/logs/{self.unknown_log_id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["deleted_snapshot"])
        self.assertTrue(self.snapshot_path.exists())
        self.assertEqual(len(self.client.get("/logs").json()), 1)

        alert = self.client.get(f"/alerts/{self.alert_id}").json()
        self.assertIsNone(alert["detection_log_id"])
        self.assertEqual(
            alert["snapshot_url"],
            f"/alerts/{self.alert_id}/snapshot",
        )

    def test_delete_log_removes_unreferenced_snapshot_file(self):
        standalone_snapshot = self.snapshots_dir / "standalone.jpg"
        standalone_snapshot.write_bytes(b"\xff\xd8standalone\xff\xd9")
        standalone_log = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                track_id,
                status,
                confidence,
                snapshot_path
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                self.camera_id,
                3,
                "unknown",
                0.31,
                str(standalone_snapshot),
            ),
        )
        self.connection.commit()

        response = self.client.delete(f"/logs/{standalone_log.lastrowid}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted_snapshot"])
        self.assertFalse(standalone_snapshot.exists())

    def test_delete_all_logs_removes_rows_and_keeps_alert_snapshot(self):
        response = self.client.delete("/logs/all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_count"], 2)
        self.assertEqual(response.json()["deleted_snapshots"], 0)
        self.assertEqual(self.client.get("/logs").json(), [])
        self.assertTrue(self.snapshot_path.exists())
        alert = self.client.get(f"/alerts/{self.alert_id}").json()
        self.assertIsNone(alert["detection_log_id"])

    def test_delete_alert_removes_row_and_preserves_log_snapshot(self):
        response = self.client.delete(f"/alerts/{self.alert_id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["deleted_snapshot"])
        self.assertTrue(self.snapshot_path.exists())
        self.assertEqual(self.client.get("/alerts").json(), [])
        self.assertEqual(len(self.client.get("/logs").json()), 2)

    def test_delete_alert_removes_unreferenced_snapshot_file(self):
        standalone_snapshot = self.snapshots_dir / "alert-only.jpg"
        standalone_snapshot.write_bytes(b"\xff\xd8alert-only\xff\xd9")
        alert = self.connection.execute(
            """
            INSERT INTO alerts (
                session_id,
                camera_id,
                alert_type,
                message,
                snapshot_path
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                1,
                self.camera_id,
                "unknown_person",
                "Alert-only snapshot",
                str(standalone_snapshot),
            ),
        )
        self.connection.commit()

        response = self.client.delete(f"/alerts/{alert.lastrowid}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted_snapshot"])
        self.assertFalse(standalone_snapshot.exists())

    def test_delete_all_alerts_removes_rows_and_keeps_log_snapshot(self):
        response = self.client.delete("/alerts/all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_count"], 1)
        self.assertEqual(response.json()["deleted_snapshots"], 0)
        self.assertEqual(self.client.get("/alerts").json(), [])
        self.assertTrue(self.snapshot_path.exists())
        self.assertEqual(len(self.client.get("/logs").json()), 2)


if __name__ == "__main__":
    unittest.main()
