import sqlite3
import sys
from backend.services.qa_service import QAService
from backend.app.schemas import QAAskRequest

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend/database/app.db')
conn.row_factory = sqlite3.Row

qa = QAService(conn)

test_questions = [
    "Trong video có ai trộm xe máy không?",
    "Có đánh nhau không?",
    "Trong video có xảy ra đánh nhau không?",
    "Có sự kiện nguy hiểm nào không?",
    "Có ai cướp xe không?",
    "Có cháy nổ gì không?",
    "Có ai mặc áo đỏ không?",
]

for q in test_questions:
    print(f"\n==================== Q: {q} ====================")
    try:
        # Test 1: không truyền video_id (hỏi trên conversation 22)
        res = qa.ask(QAAskRequest(question=q, conversation_id=22))
        print("Response:", res.response_vi)
        print("Evidences count:", len(res.evidences))
        for ev in res.evidences:
            print("  Evidence:", ev.event_type, ev.detected_label, ev.confidence, ev.snapshot_path)
    except Exception as e:
        print("Error:", e)

