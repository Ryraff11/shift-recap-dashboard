import re
from datetime import datetime

KW_OPEN = re.compile(r'\b(open(ing)?|morning)\b', re.I)
KW_MID = re.compile(r'\bmid\b', re.I)
KW_CLOSE = re.compile(r'\b(close|closing|night)\b', re.I)
SUBSTR_CLOSE = re.compile(r'clos', re.I)  # catches typos like "closere"
TIME_RANGE = re.compile(r'\b(\d{3,4})\s*-\s*\d{1,4}\b')
AM_TOKEN = re.compile(r'\bam\b', re.I)
PM_TOKEN = re.compile(r'\bpm\b', re.I)

def start_hour_from_range(match_str):
    n = int(match_str)
    if n < 100:  # e.g. '5' unlikely, guard
        return n
    if len(match_str) == 3:  # e.g. 445 -> 4:45
        return int(match_str[0])
    else:  # 4 digits, e.g. 1145 -> 11, 1200 -> 12
        return int(match_str[:2])

def parse_shift(text, submission_dt):
    m = KW_OPEN.search(text)
    if m: return 'Open', 'keyword'
    m = KW_MID.search(text)
    if m: return 'Mid', 'keyword'
    m = KW_CLOSE.search(text)
    if m: return 'Close', 'keyword'
    if SUBSTR_CLOSE.search(text):
        return 'Close', 'substr-typo'
    m = TIME_RANGE.search(text)
    if m:
        h = start_hour_from_range(m.group(1))
        if 4 <= h <= 9: return 'Open', 'time-range'
        if 10 <= h <= 15: return 'Mid', 'time-range'
        return 'Close', 'time-range'
    if AM_TOKEN.search(text):
        return 'Open', 'am-token'
    # PM token or nothing at all -> fall back to submission hour
    hr = submission_dt.hour
    if 4 <= hr <= 15: return 'Open', 'submission-hour-fallback'
    if 16 <= hr <= 20: return 'Mid', 'submission-hour-fallback'
    return 'Close', 'submission-hour-fallback'

if __name__ == '__main__':
    import csv
    with open('auburn_recap_raw.csv', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    data = rows[1:]

    TODAY = datetime(2026,7,25)
    DAYS = 30
    TODAY_INDEX = DAYS-1
    def day_index_for(dt):
        return TODAY_INDEX - (TODAY.date() - dt.date()).days

    from collections import Counter
    method_counts = Counter()
    for r in data:
        ts = r[0].strip()
        if not ts: continue
        dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        di = day_index_for(dt)
        if not (0 <= di <= TODAY_INDEX): continue
        shift, method = parse_shift(r[1], dt)
        method_counts[method] += 1
        if method != 'keyword':
            print(f'  {method:28s} -> {shift:6s} | {repr(r[1])} | submitted {dt.strftime("%-I:%M %p")}')
    print()
    print('Method breakdown:', dict(method_counts))
