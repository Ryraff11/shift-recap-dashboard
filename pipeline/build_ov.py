"""OV builder — columns match Fair Oaks. Many recaps use a time range instead of an
Open/Mid/Close word, so infer the shift from submission time when no keyword is present,
then reuse build_shop()."""
import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo

exec(open('build_shop.py').read().split("if __name__")[0])  # reuse build_shop() + helpers

RAW = 'ov_recap_raw.csv'
PREPPED = 'ov_recap_prepped.csv'
SHIFT_WORD = re.compile(r'\b(open(ing)?|morning|mid|close|closing|night)\b', re.I)

def infer_shift_from_time(dt):
    h = dt.hour + dt.minute / 60
    if h < 15:  return 'Open'   # opens due 12:15pm; morning submissions
    if h < 21:  return 'Mid'    # mids due 6:15pm; afternoon/evening
    return 'Close'              # closes due 11:30pm; late night

def main():
    with open(RAW, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header, data = rows[0], rows[1:]
    out = [header]
    for r in data:
        if not r or not r[0].strip():
            out.append(r); continue
        if len(r) > 1 and not SHIFT_WORD.search(r[1]):
            try:
                dt = datetime.strptime(r[0].strip(), '%m/%d/%Y %H:%M:%S')
                r = list(r); r[1] = f"{r[1]} {infer_shift_from_time(dt)}"
            except ValueError:
                pass
        out.append(r)
    with open(PREPPED, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerows(out)

    TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
    records = build_shop('OV', PREPPED, {'Open': (12, 15), 'Mid': (18, 15), 'Close': (23, 30)}, TODAY)
    with open('ov_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} OV records built')
    print(f"{sum(1 for x in records if x['isLate'])} of {len(records)} submitted late")

if __name__ == '__main__':
    main()
