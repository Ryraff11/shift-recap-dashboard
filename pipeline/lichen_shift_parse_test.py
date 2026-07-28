import re
from datetime import datetime

KW_OPEN = re.compile(r'\b(open(ing)?|morning|morn\w*)\b', re.I)
KW_MID = re.compile(r'\bmid\b', re.I)
KW_CLOSE = re.compile(r'\b(close|closing|night)\b', re.I)
TIME_AMPM = re.compile(r'\b(\d{1,2})(:\d{2})?\s*(am|pm)\b', re.I)
OPEN_START_SIGNATURE = re.compile(r'4:4[4-5]')  # "4:45" is the universal Dutch Bros open-shift start time we've seen at every shop

def parse_shift(text, submission_dt):
    if KW_OPEN.search(text): return 'Open', 'keyword'
    if KW_MID.search(text): return 'Mid', 'keyword'
    if KW_CLOSE.search(text): return 'Close', 'keyword'
    if OPEN_START_SIGNATURE.search(text): return 'Open', 'open-start-signature'
    m = TIME_AMPM.search(text)
    if m:
        hour = int(m.group(1))
        ampm = m.group(3).lower()
        if ampm == 'am':
            return 'Open', 'time-ampm'
        else:
            if hour == 12 or 1 <= hour <= 6:
                return 'Mid', 'time-ampm'
            return 'Close', 'time-ampm'
    hr = submission_dt.hour
    if 4 <= hr <= 12: return 'Open', 'submission-hour-fallback'
    if 13 <= hr <= 19: return 'Mid', 'submission-hour-fallback'
    return 'Close', 'submission-hour-fallback'

if __name__ == '__main__':
    import csv
    from collections import Counter
    with open('lichen_recap_raw.csv', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    data = rows[1:]

    TODAY = datetime(2026,7,25)
    DAYS = 30
    TODAY_INDEX = DAYS-1
    def day_index_for(dt):
        return TODAY_INDEX - (TODAY.date() - dt.date()).days

    method_counts = Counter()
    for r in data:
        ts = r[0].strip()
        if not ts: continue
        try:
            dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        except ValueError:
            continue
        di = day_index_for(dt)
        if not (0 <= di <= TODAY_INDEX): continue
        shift, method = parse_shift(r[1], dt)
        method_counts[method] += 1
        if method != 'keyword':
            print(f'  {method:28s} -> {shift:6s} | {repr(r[1])} | submitted {dt.strftime("%-I:%M %p")}')
    print()
    print('Method breakdown:', dict(method_counts))
