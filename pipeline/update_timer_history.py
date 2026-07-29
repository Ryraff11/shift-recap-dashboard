"""
Accumulates HME timer data into a persistent history file (hme_timer_history.json),
then injects the current 30-day window's worth of it into the dashboard HTML.

Unlike the recap pipeline, this does NOT regenerate from scratch each run --
each HME email is the only record of that day that will ever exist, so today's
newly-parsed data gets ADDED to history, never overwriting prior days.

USAGE (each scheduled run):
  1. Save each new HME "Other - Day Report" email body as a .txt file, named:
     hme_175.txt (Mad), hme_2008.txt (Lichen), hme_280.txt (Manz), hme_207.txt (Fair Oaks)
  2. Run: python3 update_timer_history.py
"""
import json, os, glob
from datetime import datetime
from zoneinfo import ZoneInfo
from parse_hme_email import parse_hme_report

HISTORY_FILE = 'hme_timer_history.json'
DASHBOARD_FILE = 'shift-recap-dashboard.html'
DAYS = 30

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def ingest_new_emails(history):
    added = []
    for txt_file in glob.glob('hme_*.txt'):
        with open(txt_file) as f:
            text = f.read()
        result = parse_hme_report(text)
        if not result:
            print(f'  SKIP {txt_file}: could not parse')
            continue
        if 'error' in result:
            print(f'  ERROR {txt_file}: {result["error"]}')
            continue
        shop = result['shop']
        date = result['date']
        history.setdefault(shop, {})
        history[shop][date] = {
            'laneTotalSec': result['lane1_avg_sec'],
            'laneTotal2Sec': result['lane2_avg_sec'],
            'totalCars': result['total_cars'],
        }
        added.append(f'{shop} / {date}')
    return added

def build_real_timer_js(history):
    """Return the last DAYS worth of history keyed BY DATE (YYYY-MM-DD), which is exactly
    what the dashboard consumes: REAL_TIMER_DATA[shop][isoForIndex(d)]. Older days fall out
    of the window so the injected payload stays bounded."""
    today = datetime.now(ZoneInfo('America/Los_Angeles')).date()

    def in_window(date_str):
        delta = (today - datetime.strptime(date_str, '%Y-%m-%d').date()).days
        return 0 <= delta <= DAYS - 1

    out = {}
    for shop, by_date in history.items():
        windowed = {ds: vals for ds, vals in by_date.items() if in_window(ds)}
        if windowed:
            out[shop] = windowed
    return out

def inject_into_dashboard(real_timer):
    # Accumulation-only guard: if the dashboard file or the REAL_TIMER_DATA marker
    # is not present, skip injection instead of crashing. History is still accumulated
    # and saved. Injection resumes automatically once the template includes the marker.
    if not os.path.exists(DASHBOARD_FILE):
        print(f'  NOTE: {DASHBOARD_FILE} not present -- skipping dashboard injection (accumulation-only mode).')
        return

    with open(DASHBOARD_FILE) as f:
        html = f.read()

    # Replace the `const REAL_TIMER_DATA = {...}` literal up to its terminating semicolon,
    # matching how refresh_dashboard.py injects it. The dashboard reads this object by date
    # (REAL_TIMER_DATA[shop][isoForIndex(d)]), so we emit a plain date-keyed JSON object.
    start_marker = 'const REAL_TIMER_DATA = '
    if start_marker not in html:
        print('  NOTE: REAL_TIMER_DATA marker not found in dashboard -- skipping injection '
              '(accumulation-only mode; injection resumes automatically once the template includes the marker).')
        return
    start_idx = html.index(start_marker)
    end_idx = html.index(';', start_idx)

    new_block = f'{start_marker}{json.dumps(real_timer)}'
    html = html[:start_idx] + new_block + html[end_idx:]

    with open(DASHBOARD_FILE, 'w') as f:
        f.write(html)

def main():
    history = load_history()
    added = ingest_new_emails(history)
    if added:
        print(f'Added {len(added)} new day(s) of timer data:')
        for a in added:
            print(f'  {a}')
    else:
        print('No new hme_*.txt files found to ingest.')
    save_history(history)

    real_timer_js = build_real_timer_js(history)
    inject_into_dashboard(real_timer_js)
    print('Dashboard updated with current 30-day timer window.')

    for shop, by_idx in real_timer_js.items():
        print(f'  {shop}: {len(by_idx)} real day(s) in current window')

if __name__ == '__main__':
    main()
