import sqlite3
import unittest

from backend.app.database import SCHEMA_VERSION, create_schema


def make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    create_schema(connection)
    return connection


def seed_camera_and_session(connection: sqlite3.Connection) -> tuple[int, int]:
    camera = connection.execute(
        """
        INSERT INTO cameras (name, source, location)
        VALUES (?, ?, ?)
        """,
        ("Laptop Webcam", "0", "Demo room"),
    )
    session = connection.execute(
        """
        INSERT INTO surveillance_sessions (camera_id)
        VALUES (?)
        """,
        (camera.lastrowid,),
    )
    connection.commit()
    return int(camera.lastrowid), int(session.lastrowid)


class DatabaseSchemaTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_connection()

    def tearDown(self):
        self.connection.close()

    def table_names(self) -> set[str]:
        rows = self.connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
        return {row["name"] for row in rows}

    def test_schema_contains_live_persistence_tables(self):
        self.assertTrue(
            {
                "people",
                "face_embeddings",
                "cameras",
                "surveillance_sessions",
                "detection_logs",
                "alerts",
                "zones",
                "video_frames",
                "detected_entities",
                "danger_threats",
                "qa_conversations",
                "qa_messages",
                "qa_evidences",
            }.issubset(self.table_names())
        )
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)

    def test_uploaded_video_analysis_has_no_persistence_table(self):
        names = self.table_names()

        self.assertNotIn("video_analysis_jobs", names)
        self.assertNotIn("uploaded_videos", names)
        self.assertNotIn("video_analysis_logs", names)

    def test_schema_creation_is_idempotent_and_preserves_data(self):
        camera_id, _ = seed_camera_and_session(self.connection)

        create_schema(self.connection)

        camera = self.connection.execute(
            "SELECT name FROM cameras WHERE id = ?",
            (camera_id,),
        ).fetchone()
        self.assertEqual(camera["name"], "Laptop Webcam")

    def test_foreign_keys_reject_session_for_missing_camera(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO surveillance_sessions (camera_id)
                VALUES (999)
                """
            )

    def test_session_status_and_counters_are_constrained(self):
        camera = self.connection.execute(
            "INSERT INTO cameras (name, source) VALUES (?, ?)",
            ("Laptop Webcam", "0"),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO surveillance_sessions (
                    camera_id,
                    status,
                    frames_processed
                )
                VALUES (?, ?, ?)
                """,
                (camera.lastrowid, "temporary_upload", 0),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO surveillance_sessions (
                    camera_id,
                    status,
                    frames_processed
                )
                VALUES (?, ?, ?)
                """,
                (camera.lastrowid, "running", -1),
            )

    def test_live_session_supports_logs_alerts_and_zones(self):
        camera_id, session_id = seed_camera_and_session(self.connection)
        detection = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                track_id,
                status,
                confidence
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, camera_id, 4, "unknown", 0.22),
        )
        alert = self.connection.execute(
            """
            INSERT INTO alerts (
                session_id,
                camera_id,
                detection_log_id,
                alert_type,
                message,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                camera_id,
                detection.lastrowid,
                "unknown_person",
                "Unknown person detected",
                0.22,
            ),
        )
        zone = self.connection.execute(
            """
            INSERT INTO zones (camera_id, name, polygon_json)
            VALUES (?, ?, ?)
            """,
            (camera_id, "Entrance", "[[0,0],[100,0],[100,100],[0,100]]"),
        )
        self.connection.commit()

        self.assertGreater(int(detection.lastrowid), 0)
        self.assertGreater(int(alert.lastrowid), 0)
        self.assertGreater(int(zone.lastrowid), 0)

    def test_deleting_member_preserves_history_and_clears_identity(self):
        member = self.connection.execute(
            "INSERT INTO people (name) VALUES (?)",
            ("Known Member",),
        )
        camera_id, session_id = seed_camera_and_session(self.connection)
        detection = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                member_id,
                status,
                confidence
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, camera_id, member.lastrowid, "known", 0.78),
        )
        self.connection.execute(
            """
            INSERT INTO alerts (
                session_id,
                camera_id,
                detection_log_id,
                member_id,
                alert_type,
                message
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                camera_id,
                detection.lastrowid,
                member.lastrowid,
                "restricted_area",
                "Restricted-area event",
            ),
        )
        self.connection.commit()

        self.connection.execute(
            "DELETE FROM people WHERE id = ?",
            (member.lastrowid,),
        )
        self.connection.commit()

        log = self.connection.execute(
            "SELECT member_id FROM detection_logs WHERE id = ?",
            (detection.lastrowid,),
        ).fetchone()
        alert = self.connection.execute(
            "SELECT member_id FROM alerts WHERE detection_log_id = ?",
            (detection.lastrowid,),
        ).fetchone()
        self.assertIsNone(log["member_id"])
        self.assertIsNone(alert["member_id"])

    def test_deleting_session_cascades_logs_and_alerts(self):
        camera_id, session_id = seed_camera_and_session(self.connection)
        detection = self.connection.execute(
            """
            INSERT INTO detection_logs (
                session_id,
                camera_id,
                status
            )
            VALUES (?, ?, ?)
            """,
            (session_id, camera_id, "unknown"),
        )
        self.connection.execute(
            """
            INSERT INTO alerts (
                session_id,
                camera_id,
                detection_log_id,
                alert_type,
                message
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                camera_id,
                detection.lastrowid,
                "unknown_person",
                "Unknown person detected",
            ),
        )
        self.connection.commit()

        self.connection.execute(
            "DELETE FROM surveillance_sessions WHERE id = ?",
            (session_id,),
        )
        self.connection.commit()

        log_count = self.connection.execute(
            "SELECT COUNT(*) FROM detection_logs"
        ).fetchone()[0]
        alert_count = self.connection.execute(
            "SELECT COUNT(*) FROM alerts"
        ).fetchone()[0]
        self.assertEqual(log_count, 0)
        self.assertEqual(alert_count, 0)

    def test_zone_names_are_unique_per_camera(self):
        camera_id, _ = seed_camera_and_session(self.connection)
        self.connection.execute(
            """
            INSERT INTO zones (camera_id, name, polygon_json)
            VALUES (?, ?, ?)
            """,
            (camera_id, "Entrance", "[[0,0],[1,0],[1,1]]"),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO zones (camera_id, name, polygon_json)
                VALUES (?, ?, ?)
                """,
                (camera_id, "Entrance", "[[2,2],[3,2],[3,3]]"),
            )


if __name__ == "__main__":
    unittest.main()
