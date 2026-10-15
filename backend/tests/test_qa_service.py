import json
import sqlite3
import unittest

from fastapi.testclient import TestClient

from backend.app.database import create_schema
from backend.app.schemas import QAAskRequest
from backend.main import create_app
from backend.routes.qa_routes import get_qa_service
from backend.services.qa_service import QAService


def make_test_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


class QAServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_test_connection()
        self.service = QAService(self.connection, api_key="")  # Dùng fallback heuristic trong test

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
            (self.camera_id, "video_01", 134.5, 3240, "snapshots/frame_3240.jpg"),
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
                "snapshots/threat_knife.jpg",
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
            (conv.id, video_id, "test.mp4", "nonexistent.mp4", "completed"),
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
            (conv.id, video_id, "test.mp4", "nonexistent.mp4", "completed"),
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


class QARoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.connection = make_test_connection()
        self.service = QAService(self.connection, api_key="")
        self.app = create_app(initialize_database=False)
        self.app.dependency_overrides[get_qa_service] = lambda: self.service
        self.client = TestClient(self.app)

    def tearDown(self):
        self.connection.close()

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
            (conv_id, video_id, "security_camera.mp4", "mock/path.mp4", "completed", 50, 50),
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
