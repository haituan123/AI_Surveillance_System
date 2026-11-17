import cv2
import sys
from ultralytics import YOLO

sys.stdout.reconfigure(encoding='utf-8')

video1 = r"D:\Code\AI_Surveillance_System\backend\data\temp_uploads\qa_22_075d442d_Quay màn hình 2026-10-16 174934.mp4"
video2 = r"D:\Code\AI_Surveillance_System\backend\data\temp_uploads\qa_22_ecf6f2a9_Quay màn hình 2026-10-16 180724.mp4"

model = YOLO(r"D:\Code\AI_Surveillance_System\backend\models\yolo\yolov8n.pt")

for vpath, vname in [(video1, "VIDEO 1 (075d - Đánh nhau)"), (video2, "VIDEO 2 (ecf6f - Trộm xe)")]:
    print(f"\n==================== {vname} ====================")
    cap = cv2.VideoCapture(vpath)
    if not cap.isOpened():
        print("Cannot open video:", vpath)
        continue
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    print(f"Total frames: {total}, FPS: {fps}")
    
    interval = max(1, int(fps)) # 1 fps
    frame_idx = 0
    all_detections = {}
    
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        if frame_idx % interval == 0:
            res = model(frame, conf=0.25, verbose=False)
            if res and len(res) > 0 and res[0].boxes is not None:
                for box in res[0].boxes:
                    cls_id = int(box.cls.item())
                    lbl = res[0].names.get(cls_id, "")
                    conf = float(box.conf.item())
                    all_detections[lbl] = all_detections.get(lbl, 0) + 1
        frame_idx += 1
    cap.release()
    print("Detections summary:", all_detections)

