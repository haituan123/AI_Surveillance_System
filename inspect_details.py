import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

con = sqlite3.connect('backend/database/app.db')
con.row_factory = sqlite3.Row

print("=== QA MESSAGES ===")
for r in con.execute("SELECT id, conversation_id, user_query_vi, response_vi, question_type FROM qa_messages").fetchall():
    print(f"ID={r['id']}, conv={r['conversation_id']}, type={r['question_type']}")
    print(f"Q: {r['user_query_vi']}")
    print(f"A: {r['response_vi']}")
    print("-" * 40)

print("\n=== THREATS GROUP BY VIDEO AND TYPE ===")
rows = con.execute("""
    SELECT vf.session_or_video_id, dt.threat_type, COUNT(*) as cnt, MAX(dt.confidence) as max_conf
    FROM danger_threats dt
    JOIN video_frames vf ON vf.id = dt.frame_id
    GROUP BY vf.session_or_video_id, dt.threat_type
""").fetchall()
for r in rows:
    print(dict(r))

print("\n=== SECURITY EVENTS ===")
for r in con.execute("SELECT * FROM security_events").fetchall():
    print(dict(r))

print("\n=== DETECTED ENTITIES SUMMARY ===")
rows = con.execute("""
    SELECT vf.session_or_video_id, de.label, de.entity_type, COUNT(*) as cnt
    FROM detected_entities de
    JOIN video_frames vf ON vf.id = de.frame_id
    GROUP BY vf.session_or_video_id, de.label, de.entity_type
""").fetchall()
for r in rows:
    print(dict(r))
