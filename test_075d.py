import cv2
import sqlite3
from ultralytics import YOLO
from backend.services.frame_indexer_service import FrameIndexerService
from backend.ai.contracts import FrameAnalysis, TrackAnalysis, BoundingBox
from backend.app.database import create_schema

video_path = r"D:\Code\AI_Surveillance_System\backend\data\temp_uploads\qa_22_075d442d_Quay màn hình 2026-10-16 174934.mp4"
cap = cv2.VideoCapture(video_path)
model = YOLO(r"D:\Code\AI_Surveillance_System\backend\models\yolo\yolov8n.pt")

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
create_schema(conn)

indexer = FrameIndexerService(conn)

frame_idx = 0
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    if frame_idx % int(fps) == 0:
        res = model(frame, conf=0.25, verbose=False)
        raw_dets = []
        person_tracks = []
        tid = 1
        if res and len(res) > 0 and res[0].boxes is not None:
            for box in res[0].boxes:
                cls_id = int(box.cls.item())
                lbl = res[0].names.get(cls_id, "")
                conf = float(box.conf.item())
                coords = box.xyxy[0].cpu().numpy().astype(int)
                d = {
                    "label": lbl,
                    "confidence": conf,
                    "x1": int(coords[0]), "y1": int(coords[1]),
                    "x2": int(coords[2]), "y2": int(coords[3]),
                }
                raw_dets.append(d)
                if lbl == "person":
                    person_tracks.append(
                        TrackAnalysis(
                            track_id=tid,
                            bounding_box=BoundingBox(d["x1"], d["y1"], d["x2"], d["y2"]),
                            person_confidence=conf,
                            status="unknown",
                            member_id=None,
                            similarity=None,
                            face_confidence=None,
                        )
                    )
                    tid += 1
        
        analysis = FrameAnalysis(
            frame_index=frame_idx,
            timestamp_seconds=frame_idx / fps,
            width=frame.shape[1],
            height=frame.shape[0],
            tracks=tuple(person_tracks),
        )
        
        indexer.index_frame(
            frame,
            session_or_video_id="test_075d",
            timestamp_seconds=frame_idx / fps,
            frame_number=frame_idx,
            analysis=analysis,
            raw_object_detections=raw_dets,
        )
    frame_idx += 1

indexer.flush("test_075d")
cap.release()

print("=== DETECTED ENTITIES 075d ===")
for r in conn.execute("SELECT label, count(*) FROM detected_entities GROUP BY label").fetchall():
    print(dict(r))

print("=== DANGER THREATS 075d ===")
for r in conn.execute("SELECT threat_type, count(*) FROM danger_threats GROUP BY threat_type").fetchall():
    print(dict(r))

print("=== SECURITY EVENTS 075d ===")
for r in conn.execute("SELECT event_type, count(*), max(confidence) FROM security_events GROUP BY event_type").fetchall():
    print(dict(r))

