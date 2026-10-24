import json
import sqlite3
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.database import create_schema
from backend.app.schemas import QAAskRequest
from backend.main import create_app
from backend.routes.qa_routes import get_qa_service
from backend.services.qa_service import QAService, QAVideoCleanupError
from backend.services.qa_video_index_manager import QAVideoIndexManager, QAVideoIndexStopTimeoutError


def make_test_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


class QAServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_test_connection()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshots = self.root / "snapshots"
        self.uploads = self.root / "uploads"
        self.snapshots.mkdir()
        self.uploads.mkdir()
        self.service = QAService(
            self.connection, api_key="", snapshots_dir=self.snapshots, uploads_dir=self.uploads
        )  # Dùng fallback heuristic trong test
        self.frame_snapshot = self.snapshots / "frame_3240.jpg"
        self.threat_snapshot = self.snapshots / "threat_knife.jpg"
        self.frame_snapshot.write_bytes(b"frame snapshot")
        self.threat_snapshot.write_bytes(b"threat snapshot")

        # Seed camera & video frames & entities
        cam = self.connection.execute(
            "INSERT INTO cameras (name, source) VALUES (?, ?)",
            ("CCTV Cửa hàng", "0"),
        )
        self.camera_id = int(cam.lastrowid)

        vf = self.connection.execute(
            """
            INSERT INTO video_frames (
                camera_id, session_or_video_id, timestamp_seconds, frame_number, frame_path
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.camera_id, "video_01", 134.5, 3240, str(self.frame_snapshot)),
        )
        self.frame_id = int(vf.lastrowid)

        # Seed entity (người mặc áo đen lấy balo)
        self.connection.execute(
            """
            INSERT INTO detected_entities (
                frame_id, entity_type, label, bbox_json, clothing_top_color, action_label
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.frame_id,
                "person",
                "backpack",
                json.dumps([100, 200, 300, 400]),
                "black",
                "taking_object",
            ),
        )

        # Seed danger threat (cầm dao)
        self.connection.execute(
            """
            INSERT INTO danger_threats (
                frame_id, threat_type, confidence, snapshot_path, description_en
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.frame_id,
                "knife_threat",
                0.92,
                str(self.threat_snapshot),
                "Person holding a knife",
            ),
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def test_create_and_list_conversations(self):
        conv = self.service.create_conversation("Hỏi an ninh buổi sáng")
        self.assertEqual(conv.title, "Hỏi an ninh buổi sáng")

        convs = self.service.list_conversations()
        self.assertEqual(len(convs), 1)
        self.assertEqual(convs[0].id, conv.id)

    def test_ask_object_taking_question_generates_evidence(self):
        req = QAAskRequest(question="Có ai lấy chiếc balo trên bàn không?")
        msg = self.service.ask(req)

        self.assertIn("balo", msg.response_vi.lower())
        self.assertEqual(msg.question_type, "object_reasoning")
        self.assertGreater(len(msg.evidences), 0)
        self.assertAlmostEqual(msg.evidences[0].start_timestamp, 134.5, delta=1.0)
        self.assertIsNotNone(msg.evidences[0].highlight_bbox)

    def test_ask_threat_question_identifies_knife_danger(self):
        req = QAAskRequest(question="Có ai cầm dao đe dọa không?")
        msg = self.service.ask(req)

        self.assertEqual(msg.question_type, "threat")
        self.assertIn("nguy hiểm", msg.response_vi.lower())
        self.assertGreater(len(msg.evidences), 0)
        self.assertEqual(msg.evidences[0].frame_id, self.frame_id)

    def test_conversation_detail_and_delete(self):
        conv = self.service.create_conversation("Kiểm tra chi tiết")
        req = QAAskRequest(question="Có ai lạ vào phòng không?", conversation_id=conv.id)
        self.service.ask(req)

        detail = self.service.get_conversation_detail(conv.id)
        self.assertEqual(len(detail.messages), 1)

        self.service.delete_conversation(conv.id)
        convs = self.service.list_conversations()
        self.assertEqual(len(convs), 0)


    def test_upload_and_list_videos(self):
        conv = self.service.create_conversation("Upload Video Conv")
        
        # Test directly inserting an uploaded video record
        self.connection.execute(
            """
            INSERT INTO qa_uploaded_videos (
                conversation_id, video_id, filename, file_path, status, total_frames, processed_frames
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (conv.id, "qa_upload_test123", "security_clip.mp4", "temp/security_clip.mp4", "completed", 100, 100),
        )
        self.connection.commit()

        videos = self.service.list_uploaded_videos(conv.id)
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0].video_id, "qa_upload_test123")
        self.assertEqual(videos[0].filename, "security_clip.mp4")

        # Test get status
        status = self.service.get_uploaded_video_status("qa_upload_test123")
        self.assertEqual(status.status, "completed")
        self.assertEqual(status.total_frames, 100)

    def test_delete_uploaded_video_cascades_frames_and_entities(self):
        conv = self.service.create_conversation("Upload Delete Conv")
        video_id = "qa_upload_del_test"

        self.connection.execute(
            """
            INSERT INTO qa_uploaded_videos (
                conversation_id, video_id, filename, file_path, status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (conv.id, video_id, "test.mp4", str(self.uploads / "absent.mp4"), "completed"),
        )
        vf = self.connection.execute(
            """
            INSERT INTO video_frames (camera_id, session_or_video_id, timestamp_seconds, frame_number, frame_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (None, video_id, 10.0, 300, ""),
        )
        frame_id = int(vf.lastrowid)
        self.connection.execute(
            """
            INSERT INTO detected_entities (frame_id, entity_type, label, bbox_json)
            VALUES (?, ?, ?, ?)
            """,
            (frame_id, "person", "suspicious", json.dumps([0, 0, 10, 10])),
        )
        self.connection.commit()

        # Delete the uploaded video
        self.service.delete_uploaded_video(video_id)

        # Verify video record deleted
        vid_row = self.connection.execute("SELECT * FROM qa_uploaded_videos WHERE video_id = ?", (video_id,)).fetchone()
        self.assertIsNone(vid_row)

        # Verify frame deleted
        frame_row = self.connection.execute("SELECT * FROM video_frames WHERE session_or_video_id = ?", (video_id,)).fetchone()
        self.assertIsNone(frame_row)

        # Verify entity cascade deleted
        ent_row = self.connection.execute("SELECT * FROM detected_entities WHERE frame_id = ?", (frame_id,)).fetchone()
        self.assertIsNone(ent_row)

    def test_delete_conversation_cascades_uploaded_videos_and_frames(self):
        conv = self.service.create_conversation("Cascade Conv")
        video_id = "qa_upload_cascade_test"

        self.connection.execute(
            """
            INSERT INTO qa_uploaded_videos (
                conversation_id, video_id, filename, file_path, status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (conv.id, video_id, "test.mp4", str(self.uploads / "absent.mp4"), "completed"),
        )
        self.connection.execute(
            """
            INSERT INTO video_frames (camera_id, session_or_video_id, timestamp_seconds, frame_number, frame_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (None, video_id, 5.0, 150, ""),
        )
        self.connection.commit()

        # Delete conversation
        self.service.delete_conversation(conv.id)

        # Verify uploaded video and frames are gone
        vid_row = self.connection.execute("SELECT * FROM qa_uploaded_videos WHERE video_id = ?", (video_id,)).fetchone()
        self.assertIsNone(vid_row)
        frame_row = self.connection.execute("SELECT * FROM video_frames WHERE session_or_video_id = ?", (video_id,)).fetchone()
        self.assertIsNone(frame_row)


class QACleanupTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshots = self.root / "snapshots"
        self.uploads = self.root / "uploads"
        self.snapshots.mkdir()
        self.uploads.mkdir()
        self.connection = make_test_connection()
        self.addCleanup(self.connection.close)
        self.manager = QAVideoIndexManager()
        self.service = QAService(
            self.connection, api_key="", index_manager=self.manager,
            snapshots_dir=self.snapshots, uploads_dir=self.uploads,
        )
        self.conversation = self.service.create_conversation("Cleanup")

    def seed_video(self, video_id="qa_cleanup", *, shared_snapshot=False):
        snapshot = self.snapshots / f"{video_id}.jpg"
        threat = snapshot if shared_snapshot else self.snapshots / f"{video_id}_threat.jpg"
        input_path = self.uploads / f"{video_id}.mp4"
        for path in (snapshot, threat, input_path):
            path.write_bytes(b"test data")
        self.connection.execute(
            "INSERT INTO qa_uploaded_videos (conversation_id, video_id, filename, file_path, status) "
            "VALUES (?, ?, 'test.mp4', ?, 'completed')",
            (self.conversation.id, video_id, str(input_path)),
        )
        frame_id = self.connection.execute(
            "INSERT INTO video_frames (session_or_video_id, timestamp_seconds, frame_number, frame_path) "
            "VALUES (?, 0, 0, ?)", (video_id, str(snapshot)),
        ).lastrowid
        self.connection.execute(
            "INSERT INTO detected_entities (frame_id, entity_type, label, bbox_json) "
            "VALUES (?, 'person', 'person', '[]')", (frame_id,),
        )
        self.connection.execute(
            "INSERT INTO danger_threats (frame_id, threat_type, confidence, snapshot_path) "
            "VALUES (?, 'knife_threat', 0.9, ?)", (frame_id, str(threat)),
        )
        message_id = self.connection.execute(
            "INSERT INTO qa_messages (conversation_id, user_query_vi, translated_query_en, response_vi) "
            "VALUES (?, 'question', 'question', 'answer')", (self.conversation.id,),
        ).lastrowid
        for fk, path in ((frame_id, snapshot), (None, snapshot), (None, threat)):
            self.connection.execute(
                "INSERT INTO qa_evidences (message_id, frame_id, start_timestamp, end_timestamp, snapshot_path) "
                "VALUES (?, ?, 0, 1, ?)", (message_id, fk, str(path)),
            )
        self.connection.commit()
        return snapshot, threat, input_path

    def count(self, table):
        return self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def assert_video_data_gone(self):
        for table in ("video_frames", "detected_entities", "danger_threats", "qa_evidences", "qa_uploaded_videos"):
            self.assertEqual(self.count(table), 0, table)

    def test_delete_completed_video_removes_files_and_stale_evidence(self):
        files = self.seed_video()
        self.assertTrue(all(path.exists() for path in files))
        self.assertEqual(self.count("qa_evidences"), 3)
        self.service.delete_uploaded_video("qa_cleanup")
        self.assertTrue(all(not path.exists() for path in files))
        self.assert_video_data_gone()
        self.assertEqual(self.count("qa_messages"), 1)
        self.assertEqual(self.count("qa_conversations"), 1)

    def test_duplicate_snapshot_is_unlinked_only_once(self):
        snapshot, _, input_path = self.seed_video(shared_snapshot=True)
        original = Path.unlink
        calls = []

        def unlink(path, *args, **kwargs):
            calls.append(path)
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", unlink):
            self.service.delete_uploaded_video("qa_cleanup")
        self.assertEqual(calls.count(snapshot), 1)
        self.assertFalse(input_path.exists())
        self.assert_video_data_gone()

    def test_delete_removes_snapshot_alias_evidence_and_preserves_unrelated_paths(self):
        snapshot, threat, _ = self.seed_video()
        (self.snapshots / "subdir").mkdir()
        message_id = self.connection.execute("SELECT id FROM qa_messages").fetchone()[0]
        aliases = [
            str(self.snapshots / "subdir" / ".." / path.name)
            for path in (snapshot, threat)
        ]
        outside = self.root / "outside.jpg"
        unrelated = self.snapshots / "unrelated.jpg"
        outside.write_bytes(b"keep outside")
        unrelated.write_bytes(b"keep unrelated")
        preserved_paths = [str(unrelated), str(outside), "bad\x00path"]
        for path in aliases + preserved_paths:
            self.connection.execute(
                "INSERT INTO qa_evidences (message_id, frame_id, start_timestamp, end_timestamp, snapshot_path) "
                "VALUES (?, NULL, 0, 1, ?)", (message_id, path),
            )
        self.connection.commit()

        self.service.delete_uploaded_video("qa_cleanup")

        self.assertFalse(snapshot.exists())
        self.assertFalse(threat.exists())
        remaining = self.connection.execute("SELECT snapshot_path FROM qa_evidences").fetchall()
        self.assertEqual({row["snapshot_path"] for row in remaining}, set(preserved_paths))
        self.assertTrue(outside.exists())
        self.assertTrue(unrelated.exists())

    def test_ask_filters_invalid_evidence_and_returns_only_persisted_rows(self):
        snapshot, threat, _ = self.seed_video()
        frame_id = self.connection.execute("SELECT id FROM video_frames").fetchone()[0]
        (self.snapshots / "subdir").mkdir()
        aliases = [str(self.snapshots / "subdir" / ".." / path.name) for path in (snapshot, threat)]
        unreferenced = self.snapshots / "unreferenced.jpg"
        unreferenced.write_bytes(b"not in index")
        missing = self.snapshots / "missing.jpg"
        self.connection.execute(
            "INSERT INTO video_frames (session_or_video_id, timestamp_seconds, frame_number, frame_path) "
            "VALUES ('other', 0, 0, ?)", (str(missing),),
        )
        self.connection.commit()
        valid = [
            {"frame_id": frame_id, "snapshot_path": aliases[0]},
            {"snapshot_path": aliases[1]},
            {"frame_id": frame_id},
            {"explanation": "Textual timeline evidence"},
        ]
        invalid = [
            {"frame_id": 99999, "snapshot_path": str(snapshot)},
            {"frame_id": 99999},
            {"snapshot_path": str(unreferenced)},
            {"snapshot_path": str(missing)},
            {"snapshot_path": str(self.root / "outside.jpg")},
            {"snapshot_path": "bad\x00path"},
        ]
        with patch.object(self.service, "_reason_with_gemini", return_value={
            "response_vi": "answer", "evidences": valid + invalid,
        }):
            message = self.service.ask(QAAskRequest(question="What happened?", conversation_id=self.conversation.id))
        self.assertEqual(len(message.evidences), len(valid))
        self.assertEqual([e.snapshot_path for e in message.evidences], aliases + ["", ""])
        persisted = self.connection.execute(
            "SELECT id, snapshot_path FROM qa_evidences WHERE message_id = ? ORDER BY id", (message.id,),
        ).fetchall()
        self.assertEqual(
            [(e.id, e.snapshot_path) for e in message.evidences],
            [(row["id"], row["snapshot_path"]) for row in persisted],
        )

    def test_ask_message_and_evidence_roll_back_together(self):
        snapshot, _, _ = self.seed_video()
        before_messages = self.count("qa_messages")
        before_evidences = self.count("qa_evidences")
        with patch.object(self.service, "_reason_with_gemini", return_value={
            "response_vi": "answer", "evidences": [
                {"snapshot_path": str(snapshot)},
                {"snapshot_path": str(snapshot), "start_timestamp": "invalid"},
            ],
        }):
            with self.assertRaises(ValueError):
                self.service.ask(QAAskRequest(question="What happened?", conversation_id=self.conversation.id))
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(self.count("qa_messages"), before_messages)
        self.assertEqual(self.count("qa_evidences"), before_evidences)

    def test_ask_validation_work_does_not_grow_with_unrelated_history(self):
        snapshot, _, _ = self.seed_video()
        frame_id = self.connection.execute("SELECT id FROM video_frames").fetchone()[0]

        def ask_and_count_paths():
            with (
                patch.object(self.service, "_canonical_snapshot_path", wraps=self.service._canonical_snapshot_path) as canonical,
                patch.object(self.service, "_reason_with_gemini", return_value={
                    "response_vi": "answer", "evidences": [{"frame_id": frame_id, "snapshot_path": str(snapshot)}],
                }),
            ):
                message = self.service.ask(QAAskRequest(
                    question="What happened?", conversation_id=self.conversation.id, session_or_video_id="qa_cleanup",
                ))
                self.assertEqual(len(message.evidences), 1)
                return canonical.call_count

        initial_calls = ask_and_count_paths()
        self.connection.executemany(
            "INSERT INTO video_frames (session_or_video_id, timestamp_seconds, frame_number, frame_path) "
            "VALUES ('unrelated', 0, ?, ?)",
            [(i, str(self.snapshots / f"unrelated_{i}.jpg")) for i in range(5000)],
        )
        self.connection.execute(
            "INSERT INTO danger_threats (frame_id, threat_type, confidence, snapshot_path) "
            "SELECT id, 'knife_threat', 0.9, frame_path || '_threat.jpg' "
            "FROM video_frames WHERE session_or_video_id = 'unrelated'"
        )
        self.connection.commit()
        self.assertEqual(ask_and_count_paths(), initial_calls)
        self.assertLessEqual(initial_calls, 10)

    def test_ask_frame_evidence_must_match_video_camera_and_snapshot(self):
        snapshot, _, _ = self.seed_video("target")
        other_snapshot, _, _ = self.seed_video("other")
        frame_id = self.connection.execute("SELECT id FROM video_frames WHERE session_or_video_id = 'target'").fetchone()[0]
        other_id = self.connection.execute("SELECT id FROM video_frames WHERE session_or_video_id = 'other'").fetchone()[0]
        camera_id = self.connection.execute("INSERT INTO cameras (name, source) VALUES ('target', '0')").lastrowid
        other_camera_id = self.connection.execute("INSERT INTO cameras (name, source) VALUES ('other', '1')").lastrowid
        self.connection.execute("UPDATE video_frames SET camera_id = ? WHERE id = ?", (camera_id, frame_id))
        self.connection.execute("UPDATE video_frames SET camera_id = ? WHERE id = ?", (other_camera_id, other_id))
        self.connection.commit()
        evidences = [
            {"frame_id": frame_id, "snapshot_path": str(snapshot)},
            {"frame_id": 99999},
            {"frame_id": other_id, "snapshot_path": str(other_snapshot)},
            {"frame_id": frame_id, "snapshot_path": str(other_snapshot)},
            {"frame_id": other_id},
        ]
        for video, camera, expected_count in (
            ("target", None, 1), (None, camera_id, 1), ("target", camera_id, 1), ("target", other_camera_id, 0),
        ):
            with self.subTest(video=video, camera=camera):
                with patch.object(self.service, "_reason_with_gemini", return_value={"response_vi": "answer", "evidences": evidences}):
                    message = self.service.ask(QAAskRequest(
                        question="What happened?", conversation_id=self.conversation.id,
                        session_or_video_id=video, camera_id=camera,
                    ))
                self.assertEqual(len(message.evidences), expected_count)
                if expected_count:
                    self.assertEqual(message.evidences[0].frame_id, frame_id)

    def test_snapshot_only_evidence_requires_current_context_provenance(self):
        self.seed_video("target")
        other_snapshot, _, _ = self.seed_video("other")
        for empty_context in (False, True):
            with self.subTest(empty_context=empty_context):
                with patch.object(self.service, "_reason_with_gemini", return_value={
                    "response_vi": "answer", "evidences": [{"snapshot_path": str(other_snapshot)}],
                }):
                    if empty_context:
                        with patch.object(self.service, "_gather_surveillance_context", return_value={"entities": [], "threats": []}):
                            message = self.service.ask(QAAskRequest(question="What happened?", conversation_id=self.conversation.id))
                    else:
                        message = self.service.ask(QAAskRequest(
                            question="What happened?", conversation_id=self.conversation.id, session_or_video_id="target",
                        ))
                self.assertTrue(other_snapshot.exists())
                self.assertEqual(message.evidences, [])

    def test_snapshot_provenance_is_revalidated_after_reasoning(self):
        snapshot, threat, _ = self.seed_video()

        def reason(**kwargs):
            frame_id = kwargs["context_data"]["entities"][0]["frame_id"]
            self.assertEqual(kwargs["context_data"]["threats"][0]["frame_id"], frame_id)
            self.connection.execute("DELETE FROM video_frames WHERE id = ?", (frame_id,))
            self.connection.commit()
            return {"response_vi": "answer", "evidences": [
                {"snapshot_path": str(snapshot)}, {"snapshot_path": str(threat)},
            ]}

        with patch.object(self.service, "_reason_with_gemini", side_effect=reason):
            message = self.service.ask(QAAskRequest(question="What happened?", conversation_id=self.conversation.id))
        self.assertTrue(snapshot.exists())
        self.assertTrue(threat.exists())
        self.assertEqual(message.evidences, [])

    def test_delete_conversation_stops_all_before_cleaning_multiple_videos(self):
        files = [*self.seed_video("first"), *self.seed_video("second")]

        def cancel_many(video_ids):
            self.assertEqual(set(video_ids), {"first", "second"})
            self.assertTrue(all(path.exists() for path in files))

        with patch.object(self.manager, "cancel_many", side_effect=cancel_many) as cancel:
            self.service.delete_conversation(self.conversation.id)
        cancel.assert_called_once()
        self.assertTrue(all(not path.exists() for path in files))
        self.assert_video_data_gone()
        self.assertEqual(self.count("qa_messages"), 0)
        self.assertEqual(self.count("qa_conversations"), 0)

    def test_unlink_failure_preserves_metadata_and_retry_is_idempotent(self):
        files = self.seed_video()
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == files[1]:
                raise PermissionError("locked file")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", unlink):
            with self.assertRaises(QAVideoCleanupError):
                self.service.delete_uploaded_video("qa_cleanup")
        for table in ("video_frames", "detected_entities", "danger_threats", "qa_uploaded_videos"):
            self.assertEqual(self.count(table), 1, table)
        self.assertEqual(self.count("qa_evidences"), 3)
        self.service.delete_uploaded_video("qa_cleanup")
        self.assert_video_data_gone()
        self.assertTrue(all(not path.exists() for path in files))

    def test_conversation_failure_keeps_metadata_for_all_videos(self):
        self.seed_video("first")
        self.seed_video("second")
        with patch.object(Path, "unlink", side_effect=OSError("locked")):
            with self.assertRaises(QAVideoCleanupError):
                self.service.delete_conversation(self.conversation.id)
        self.assertEqual(self.count("qa_uploaded_videos"), 2)
        self.assertEqual(self.count("video_frames"), 2)
        self.assertEqual(self.count("qa_evidences"), 6)
        self.assertEqual(self.count("qa_conversations"), 1)

    def test_input_unlink_failure_preserves_metadata(self):
        files = self.seed_video()
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == files[2]:
                raise OSError("input is locked")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", unlink):
            with self.assertRaises(QAVideoCleanupError):
                self.service.delete_uploaded_video("qa_cleanup")
        self.assertTrue(files[2].exists())
        self.assertEqual(self.count("video_frames"), 1)
        self.assertEqual(self.count("qa_evidences"), 3)
        self.assertEqual(self.count("qa_uploaded_videos"), 1)

    def test_video_deletion_preserves_other_videos(self):
        self.seed_video("target")
        other_files = self.seed_video("other")
        self.service.delete_uploaded_video("target")
        self.assertTrue(all(path.exists() for path in other_files))
        self.assertEqual(self.count("qa_uploaded_videos"), 1)
        self.assertEqual(self.count("video_frames"), 1)
        self.assertEqual(self.count("qa_evidences"), 3)

    def test_frame_linked_evidence_is_removed_even_without_a_snapshot_match(self):
        self.seed_video()
        self.connection.execute("UPDATE qa_evidences SET snapshot_path = '' WHERE frame_id IS NOT NULL")
        self.connection.commit()
        self.service.delete_uploaded_video("qa_cleanup")
        self.assert_video_data_gone()

    def test_stop_timeout_prevents_any_destructive_cleanup(self):
        files = self.seed_video()
        for method, action in (
            ("cancel", lambda: self.service.delete_uploaded_video("qa_cleanup")),
            ("cancel_many", lambda: self.service.delete_conversation(self.conversation.id)),
        ):
            with self.subTest(method=method):
                with patch.object(self.manager, method, side_effect=QAVideoIndexStopTimeoutError()):
                    with self.assertRaises(QAVideoIndexStopTimeoutError):
                        action()
                self.assertTrue(all(path.exists() for path in files))
                self.assertEqual(self.count("video_frames"), 1)
                self.assertEqual(self.count("qa_uploaded_videos"), 1)

    def test_untrusted_paths_cannot_delete_outside_storage(self):
        self.seed_video()
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"keep")
        for table, column in (("video_frames", "frame_path"), ("qa_uploaded_videos", "file_path")):
            with self.subTest(table=table):
                before = self.connection.execute(f"SELECT {column} FROM {table}").fetchone()[0]
                self.connection.execute(f"UPDATE {table} SET {column} = ?", (str(outside),))
                self.connection.commit()
                with self.assertRaises(QAVideoCleanupError):
                    self.service.delete_uploaded_video("qa_cleanup")
                self.assertTrue(outside.exists())
                self.assertEqual(self.count("video_frames"), 1)
                self.connection.execute(f"UPDATE {table} SET {column} = ?", (before,))
                self.connection.commit()

    def test_upload_and_retry_delegate_to_shared_manager(self):
        path = self.uploads / "new.mp4"
        path.write_bytes(b"video")
        with patch.object(self.manager, "start") as start:
            uploaded = self.service.upload_video(self.conversation.id, path, "new.mp4")
            start.assert_called_once_with(uploaded.video_id, path)
        with patch.object(self.manager, "cancel") as cancel, patch.object(self.manager, "start") as start:
            self.service.retry_uploaded_video(uploaded.video_id)
            cancel.assert_called_once_with(uploaded.video_id)
            start.assert_called_once_with(uploaded.video_id, path)
        self.assertTrue(path.exists())


class QARoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_test_connection()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshots = self.root / "snapshots"
        self.uploads = self.root / "uploads"
        self.snapshots.mkdir()
        self.uploads.mkdir()
        self.service = QAService(
            self.connection, api_key="", snapshots_dir=self.snapshots, uploads_dir=self.uploads
        )
        self.app = create_app(initialize_database=False)
        self.app.dependency_overrides[get_qa_service] = lambda: self.service
        self.client = TestClient(self.app)

    def tearDown(self):
        self.connection.close()

    def test_delete_errors_are_explicit_and_do_not_leak_paths(self):
        for method, url in (
            ("delete_uploaded_video", "/qa/videos/test"),
            ("delete_conversation", "/qa/conversations/1"),
        ):
            for error, code in (
                (QAVideoIndexStopTimeoutError("Timed out stopping Q&A video indexing; please retry"), 503),
                (QAVideoCleanupError("Could not remove Q&A video files; please retry deletion"), 500),
            ):
                with self.subTest(method=method, code=code):
                    with patch.object(self.service, method, side_effect=error):
                        response = self.client.delete(url)
                    self.assertEqual(response.status_code, code)
                    self.assertIn("retry", response.json()["detail"])
                    self.assertNotIn(str(self.root), response.text)

    def test_missing_uploaded_video_still_returns_404(self):
        self.assertEqual(self.client.delete("/qa/videos/missing").status_code, 404)

    def test_app_shutdown_stops_all_managers(self):
        with (
            patch("backend.main.ensure_runtime_directories"),
            patch("backend.main.init_db"),
            patch("backend.main.qa_video_index_manager.shutdown") as qa_shutdown,
            patch("backend.main.video_analysis_manager.shutdown") as video_shutdown,
            patch("backend.main.surveillance_manager.shutdown") as surveillance_shutdown,
        ):
            with TestClient(create_app()):
                qa_shutdown.assert_not_called()
            qa_shutdown.assert_called_once()
            video_shutdown.assert_called_once()
            surveillance_shutdown.assert_called_once()

    def test_api_conversations_flow(self):
        # 1. Create conv
        res = self.client.post("/qa/conversations", json={"title": "Test Chat"})
        self.assertEqual(res.status_code, 201)
        conv_id = res.json()["id"]

        # 2. Ask question
        ask_res = self.client.post(
            "/qa/ask",
            json={"question": "Trong video có ai lấy balo không?", "conversation_id": conv_id},
        )
        self.assertEqual(ask_res.status_code, 200)
        data = ask_res.json()
        self.assertIn("response_vi", data)
        self.assertIn("translated_query_en", data)

        # 3. Get detail
        detail_res = self.client.get(f"/qa/conversations/{conv_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(len(detail_res.json()["messages"]), 1)
        self.assertEqual(len(detail_res.json()["uploaded_videos"]), 0)

    def test_api_uploaded_video_lifecycle(self):
        # 1. Create conv
        res = self.client.post("/qa/conversations", json={"title": "Test Video Flow"})
        conv_id = res.json()["id"]

        # 2. Test upload with invalid file extension
        bad_upload = self.client.post(
            f"/qa/conversations/{conv_id}/videos",
            files={"file": ("malicious.exe", b"fake binary", "application/octet-stream")},
        )
        self.assertEqual(bad_upload.status_code, 400)

        # 3. Insert mock completed video
        video_id = "qa_upload_mock_flow"
        self.connection.execute(
            """
            INSERT INTO qa_uploaded_videos (
                conversation_id, video_id, filename, file_path, status, processed_frames, total_frames
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (conv_id, video_id, "security_camera.mp4", str(self.uploads / "absent.mp4"), "completed", 50, 50),
        )
        self.connection.commit()

        # 4. List videos
        list_res = self.client.get(f"/qa/conversations/{conv_id}/videos")
        self.assertEqual(list_res.status_code, 200)
        data = list_res.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["video_id"], video_id)
        self.assertEqual(data[0]["status"], "completed")

        # 5. Status endpoint
        status_res = self.client.get(f"/qa/videos/{video_id}/status")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["status"], "completed")

        # 6. Delete video endpoint
        del_res = self.client.delete(f"/qa/videos/{video_id}")
        self.assertEqual(del_res.status_code, 204)

        # 7. Check video is deleted
        list_after = self.client.get(f"/qa/conversations/{conv_id}/videos")
        self.assertEqual(len(list_after.json()), 0)


if __name__ == "__main__":
    unittest.main()
