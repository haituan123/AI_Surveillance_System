import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('backend/services/qa_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
for i, l in enumerate(lines):
    if 'def _fallback_heuristic_qa(' in l:
        start_idx = i
        break

print(f"Start index: {start_idx}")
for i in range(start_idx, min(start_idx + 220, len(lines))):
    print(f"{i+1}: {lines[i]}", end='')

