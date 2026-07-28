"""Accumulate HME drive-thru timer data into a persistent history file.

Reads raw inline HME "Day Report" bodies dropped into pipeline/hme_data/*.txt (the agent /
scheduled run fetches these from Gmail, since a standalone script can't call the Gmail
connector), parses each with parse_hme_email, and merges the results into
pipeline/timer_history.json:

    { "<Shop>": { "YYYY-MM-DD": {laneTotalSec, laneTotal2Sec, totalCars}, ... }, ... }

timer_history.json is committed to the repo so history GROWS over time -- each run only
adds newly-seen shop/day entries. refresh_dashboard.py injects it into the dashboard as
REAL_TIMER_DATA, and the Times/leaderboard views use real numbers on days that have them
(falling back to simulated data otherwise).
"""
import json, os, glob
from parse_hme_email import parse_inline_report

HISTORY_FILE = 'timer_history.json'
EMAIL_DIR = 'hme_data'

def main():
    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)

    files = sorted(glob.glob(os.path.join(EMAIL_DIR, '*.txt')))
    per_shop_new = {}
    new_entries = 0
    parsed = 0
    for path in files:
        with open(path, encoding='utf-8') as f:
            body = f.read()
        rec = parse_inline_report(body)
        if not rec:
            continue
        parsed += 1
        shop, date = rec['shop'], rec['date']
        shop_hist = history.setdefault(shop, {})
        if date not in shop_hist:
            per_shop_new[shop] = per_shop_new.get(shop, 0) + 1
            new_entries += 1
        shop_hist[date] = {
            'laneTotalSec': rec['laneTotalSec'],
            'laneTotal2Sec': rec['laneTotal2Sec'],
            'totalCars': rec['totalCars'],
        }

    # stable, sorted output
    history = {shop: {d: days[d] for d in sorted(days)} for shop, days in sorted(history.items())}
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

    print('=== HME timer history updated ===')
    print(f'  parsed {parsed} report file(s) from {EMAIL_DIR}/')
    all_dates = set()
    for shop, days in sorted(history.items()):
        ds = sorted(days)
        all_dates.update(ds)
        newn = per_shop_new.get(shop, 0)
        tag = f'  (+{newn} new)' if newn else ''
        span = f'[{ds[0]} .. {ds[-1]}]' if ds else ''
        print(f'  {shop:10} {len(ds):3} real day(s){tag}  {span}')
    print('  ---')
    print(f'  {len(history)} shop(s) with real timer data; {len(all_dates)} distinct real day(s) in window; {new_entries} new entry(ies) this run')
    if not history:
        print('  (nothing parsed -- populate pipeline/hme_data/ with inline "Day Report" bodies first)')

if __name__ == '__main__':
    main()
