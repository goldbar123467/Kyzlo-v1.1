import csv
import re
from pathlib import Path

# Always use the latest otq log in this directory
LOG_DIR = Path(".")
LOG_FILE = max(LOG_DIR.glob("otq_*.log"), key=lambda p: p.stat().st_mtime)

# Output CSV matches the log name
OUT_FILE = LOG_FILE.with_suffix(".csv")

LOG_PATTERN = re.compile(
    r'(?P<timestamp>\d{2}:\d{2}:\d{2})\s+\|\s+'
    r'(?P<level>\w+)\s+\|\s+'
    r'(?P<module>[^:]+):'
    r'(?P<message>.*)'
)

rows = []

with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        match = LOG_PATTERN.search(line)
        if match:
            rows.append(match.groupdict())

if not rows:
    print("⚠️ No matching log lines found")
else:
    with OUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Converted {len(rows)} rows → {OUT_FILE.resolve()}")
