import sqlite3
import cv2
import sys
from pathlib import Path
from ultralytics import YOLO

from backend.app.config import SNAPSHOTS_DIR, QA_SNAPSHOTS_DIR
from backend.services.qa_snapshot_storage import qa_video_snapshot_dir
from backend.services.frame_indexer_service import FrameIndexerService
from backend.services.gallery_service import build_analysis_runtime

sys.stdout.reconfigure(encoding='utf-8')

db_path = r"D:\Code\AI_Surveillance_System\backend\database\app.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

videos = conn.execute("""
    SELECT id, conversation_id, video_id, filename, file_path
    FROM qa_uploaded_videos
    WHERE video_id IN ('qa_upload_387f876678b4', 'qa_upload_41b3fcbb4935')
""").fetchall()

runtime = build_analysis_runtime(conn)
person_tracker = getattr(runtime.engine, "person_tracker", None)

for v in videos:
    vid = v["video_id"]
    fpath = v["file_path"]
    print(f"\n==================== RE-INDEXING {v['filename']} ({vid}) ====================")
    
    # Clean previous data for this video
    frame_ids = [r[0] for r in conn.execute("SELECT id FROM video_frames WHERE session_or_video_id = ?", (vid,)).fetchall()]
    if frame_ids:
        conn.execute(f"DELETE FROM detected_entities WHERE frame_id IN ({','.join('?' for _ in frame_ids)})", frame_ids)
        conn.execute(f"DELETE FROM danger_threats WHERE frame_id IN ({','.join('?' for _ in frame_ids)})", frame_ids)
    conn.execute("DELETE FROM security_events WHERE session_or_video_id = ?", (vid,))
    conn.execute("DELETE FROM video_frames WHERE session_or_video_id = ?", (vid,))
    conn.commit()

    cap = cv2.VideoCapture(fpath)
    if not cap.isOpened():
        print("Cannot open video:", fpath)
        continue

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    sample_interval = max(1, int(fps))

    snap_dir = qa_video_snapshot_dir(vid, qa_root=QA_SNAPSHOTS_DIR)
    indexer = FrameIndexerService(conn, snapshots_dir=snap_dir)

    frame_index = 0
    indexed_count = 0

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        
        if frame_index % sample_interval == 0:
            ts = frame_index / fps if fps > 0 else 0.0
            analysis = runtime.engine.analyze_frame(
                frame,
                frame_index=frame_index,
                timestamp_seconds=ts,
            )
            raw_dets = []
            if person_tracker is not None and hasattr(person_tracker, "detect_objects"):
                try:
                    raw_dets = person_tracker.detect_objects(frame, confidence=0.25)
                except Exception as e:
                    print("detect_objects error:", e)

            indexer.index_frame(
                frame,
                camera_id=None,
                session_or_video_id=vid,
                timestamp_seconds=ts,
                frame_number=frame_index,
                analysis=analysis,
                raw_object_detections=raw_dets,
            )
            indexed_count += 1

        frame_index += 1

    indexer.flush(vid)
    cap.release()
    conn.commit()

    print(f"Finished {vid}: {indexed_count} indexed frames.")
    
    # Check what was saved
    se = conn.execute("SELECT event_type, count(*), max(confidence) FROM security_events WHERE session_or_video_id = ? GROUP BY event_type", (vid,)).fetchall()
    print("Security events saved:", [dict(r) for r in se])
    
    dt = conn.execute("""
        SELECT dt.threat_type, count(*), max(dt.confidence)
        FROM danger_threats dt
        JOIN video_frames vf ON vf.id = dt.frame_id
        WHERE vf.session_or_video_id = ?
        GROUP BY dt.threat_type
    """, (vid,)).fetchall()
    print("Danger threats saved:", [dict(r) for r in dt])

    de = conn.execute("""
        SELECT de.label, count(*)
        FROM detected_entities de
        JOIN video_frames vf ON vf.id = de.frame_id
        WHERE vf.session_or_video_id = ?
        GROUP BY de.label
    """, (vid,)).fetchall()
    print("Detected entities saved:", [dict(r) for r in de])

conn.close()
print("\nAll re-indexing completed successfully!")
