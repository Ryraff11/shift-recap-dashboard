import re
from datetime import datetime

KW_OPEN = re.compile(r'\b(open(ing)?|morning|morn\w*)\b', re.I)
KW_MID = re.compile(r'\bmid\b', re.I)
KW_CLOSE = re.compile(r'\b(close|closing|night)\b', re.I)
OPEN_START_SIGNATURE = re.compile(r'4:?4[4-5]')  # matches "4:45" or "445"
RANGE_PATTERN = re.compile(r'(\d{1,2}(?::\d{2})?)\s*-\s*(\d{1,2}(?::\d{2})?)')
AMPM_ATTACHED = re.compile(r'(\d{1,2})\s*(am|pm)', re.I)

def parse_shift(text, submission_dt):
    if KW_OPEN.search(text): return 'Open', 'keyword'
    if KW_MID.search(text): return 'Mid', 'keyword'
    if KW_CLOSE.search(text): return 'Close', 'keyword'
    if OPEN_START_SIGNATURE.search(text): return 'Open', 'open-start-signature'
    # explicit "Xam"/"Xpm" attached directly to a number -- trust the stated text
    am_pm_match = AMPM_ATTACHED.search(text)
    if am_pm_match:
        hour = int(am_pm_match.group(1))
        ampm = am_pm_match.group(2).lower()
        if ampm == 'am':
            if 4 <= hour <= 9: return 'Open', 'ampm-attached'
            return 'Mid', 'ampm-attached'  # 10-11am starts are Mid here
        else:
            if hour == 12 or 1 <= hour <= 6: return 'Mid', 'ampm-attached'
            return 'Close', 'ampm-attached'
    # take the LAST hyphenated number-pair in the string -- dates can also use hyphens
    # and appear earlier, so the rightmost match is the actual shift-time range
    matches = list(RANGE_PATTERN.finditer(text))
    if matches:
        start_hour = int(matches[-1].group(1).split(':')[0])
        end_hour = int(matches[-1].group(2).split(':')[0])
        if 9 <= start_hour <= 13:
            return 'Mid', 'range-start-hour'
        if 1 <= start_hour <= 8:
            # ambiguous: a small number here is usually a PM close-start (6/7/8pm), but
            # occasionally someone starts an Open shift a bit later than 4:45 (e.g. "7-1230pm").
            # Use submission time + a small end-hour as a tie-breaker toward Open in that case.
            sub_hr = submission_dt.hour
            if 4 <= sub_hr <= 13 and end_hour == 12:
                return 'Open', 'range-start-hour-am-correction'
            return 'Close', 'range-start-hour'
    hr = submission_dt.hour
    if 4 <= hr <= 13: return 'Open', 'submission-hour-fallback'
    if 14 <= hr <= 20: return 'Mid', 'submission-hour-fallback'
    return 'Close', 'submission-hour-fallback'

DAY_GROUP_A = {0, 2, 5}   # Monday, Wednesday, Saturday
def day_group(weekday):
    return 'A' if weekday in DAY_GROUP_A else 'B'

SHIFT_CUTOFFS_BY_GROUP = {
    'A': {'Open': (10, 0), 'Mid': (18, 15), 'Close': (23, 20)},
    'B': {'Open': (12, 15), 'Mid': (19, 15), 'Close': (23, 20)},
}

if __name__ == '__main__':
    import csv
    from collections import Counter
    with open('manz_recap_raw.csv', newline='', encoding='utf-8') as f:
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
        dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        di = day_index_for(dt)
        if not (0 <= di <= TODAY_INDEX): continue
        shift, method = parse_shift(r[1], dt)
        method_counts[method] += 1
    print('Method breakdown:', dict(method_counts))
