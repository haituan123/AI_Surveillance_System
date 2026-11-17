import sqlite3

con = sqlite3.connect('backend/database/app.db')
con.row_factory = sqlite3.Row
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables in backend/database/app.db:', tables)

for t in tables:
    count = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"Table {t}: {count} rows")

if 'qa_uploaded_videos' in tables:
    print("\n--- qa_uploaded_videos ---")
    for r in con.execute("SELECT * FROM qa_uploaded_videos").fetchall():
        print(dict(r))

if 'security_events' in tables:
    print("\n--- security_events ---")
    for r in con.execute("SELECT * FROM security_events").fetchall():
        print(dict(r))

if 'danger_threats' in tables:
    print("\n--- danger_threats sample ---")
    for r in con.execute("SELECT threat_type, confidence, snapshot_path, description_en FROM danger_threats LIMIT 10").fetchall():
        print(dict(r))

if 'qa_messages' in tables:
    print("\n--- qa_messages ---")
    for r in con.execute("SELECT * FROM qa_messages ORDER BY id DESC LIMIT 5").fetchall():
        print(dict(r))

if 'qa_evidences' in tables:
    print("\n--- qa_evidences ---")
    for r in con.execute("SELECT * FROM qa_evidences ORDER BY id DESC LIMIT 5").fetchall():
        print(dict(r))

