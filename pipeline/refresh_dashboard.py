"""
Master orchestrator: pulls the 7 per-shop build scripts together, re-keys
Antelope/Fair Oaks labels, resolves nicknames, and injects fresh data into
the dashboard HTML template -- all in one command.

USAGE:
  Place these 7 CSVs in the same folder as this script (exact filenames matter):
    antelope_recap_raw.csv
    fairoaks_recap_raw.csv
    auburn_recap_raw.csv
    madhouse_recap_raw.csv
    lichen_recap_raw.csv
    fireside_recap_raw.csv
    manz_recap_raw.csv
  Also place shift-recap-dashboard.html (the current dashboard file) in this folder.
  Then run:  python3 refresh_dashboard.py
  It overwrites shift-recap-dashboard.html with fresh data for all 7 shops.
"""
import json, subprocess, sys
from datetime import datetime
from zoneinfo import ZoneInfo

BUILD_SCRIPTS = [
    'build_antelope.py',
    'build_shop.py',       # Fair Oaks
    'build_auburn.py',
    'build_madhouse.py',
    'build_lichen.py',
    'build_fireside.py',
    'build_manz.py',
    'build_ov.py',
]

REQUIRED_CSVS = [
    'antelope_recap_raw.csv', 'fairoaks_recap_raw.csv', 'auburn_recap_raw.csv',
    'madhouse_recap_raw.csv', 'lichen_recap_raw.csv', 'fireside_recap_raw.csv',
    'manz_recap_raw.csv', 'ov_recap_raw.csv',
]

DASHBOARD_FILE = 'shift-recap-dashboard.html'

LABEL_MAP = {
    'staffing':'Staffing', 'lineTimes':'Line times / leaderboard',
    'teamPlayer':'Team player / needed to step up', 'tardy':'Tardy / early out',
    'foodInventory':'Food inventory sheet', 'safety':'Safety hazards',
    'xbro':'Xbro / non-negotiables', 'comments':'Additional comments',
    'closingVerifone':'Closing: Verifone WiFi', 'closingChecklist':'Closing checklist',
}

def step(msg):
    print(f'\n=== {msg} ===')

def main():
    import os
    missing = [c for c in REQUIRED_CSVS if not os.path.exists(c)]
    if missing:
        print('ERROR: missing required CSV files:', missing)
        print('Pull these sheets from Google Drive and save them with these exact names first.')
        sys.exit(1)
    if not os.path.exists(DASHBOARD_FILE):
        print(f'ERROR: {DASHBOARD_FILE} not found in this folder.')
        sys.exit(1)

    step('Running per-shop build scripts')
    for script in BUILD_SCRIPTS:
        print(f'  running {script} ...')
        result = subprocess.run([sys.executable, script], capture_output=True, text=True)
        if result.returncode != 0:
            print(f'  FAILED: {script}')
            print(result.stderr)
            sys.exit(1)
        for line in result.stdout.strip().split('\n'):
            print(f'    {line}')

    step('Re-keying Antelope / Fair Oaks fullRecap labels')
    for shop_file in ['antelope_records_full_window.json', 'fairoaks_records_full_window.json']:
        with open(shop_file) as f:
            recs = json.load(f)
        for r in recs:
            if r.get('fullRecap'):
                r['fullRecap'] = {LABEL_MAP.get(k, k): v for k, v in r['fullRecap'].items()}
        with open(shop_file, 'w') as f:
            json.dump(recs, f, indent=2)
    print('  done')

    step('Resolving nicknames across all shops')
    result = subprocess.run([sys.executable, 'resolve_nicknames.py'], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(1)

    step('Attributing after-midnight Close recaps to the prior shift-day')
    # A Close recap filed after midnight (00:00-05:00) belongs to the shift that ran the
    # previous evening, not the new calendar day. Roll it back one dayIndex and keep it
    # marked late, so it doesn't surface as a "late today" before today's windows open.
    shop_json_files = [
        'antelope_records_full_window.json', 'fairoaks_records_full_window.json',
        'auburn_records_full_window.json', 'madhouse_records_full_window.json',
        'lichen_records_full_window.json', 'fireside_records_full_window.json',
        'manz_records_full_window.json', 'ov_records_full_window.json',
    ]
    rolled = 0
    for jf in shop_json_files:
        with open(jf) as f:
            recs = json.load(f)
        for r in recs:
            if r.get('shift') == 'Close' and r.get('timestamp'):
                try:
                    ts = datetime.strptime(r['timestamp'], '%m/%d/%Y %H:%M:%S')
                except ValueError:
                    continue
                if ts.hour < 5:
                    r['dayIndex'] = r.get('dayIndex', 0) - 1
                    r['isLate'] = True
                    rolled += 1
        recs = [r for r in recs if r.get('dayIndex', 0) >= 0]
        with open(jf, 'w') as f:
            json.dump(recs, f, indent=2)
    print(f'  rolled {rolled} after-midnight Close recap(s) back to the prior shift-day')

    step('Injecting fresh data into dashboard HTML')
    with open(DASHBOARD_FILE) as f:
        html = f.read()

    shop_files = {
        'REAL_ANTELOPE_RECORDS': 'antelope_records_full_window.json',
        'REAL_FAIROAKS_RECORDS': 'fairoaks_records_full_window.json',
        'REAL_AUBURN_RECORDS': 'auburn_records_full_window.json',
        'REAL_MADHOUSE_RECORDS': 'madhouse_records_full_window.json',
        'REAL_LICHEN_RECORDS': 'lichen_records_full_window.json',
        'REAL_FIRESIDE_RECORDS': 'fireside_records_full_window.json',
        'REAL_MANZ_RECORDS': 'manz_records_full_window.json',
        'REAL_OV_RECORDS': 'ov_records_full_window.json',
    }
    var_names = list(shop_files.keys())
    for i, var_name in enumerate(var_names):
        with open(shop_files[var_name]) as f:
            payload = json.dumps(json.load(f), indent=2)
        start_marker = f"const {var_name} = "
        if i + 1 < len(var_names):
            end_marker = f"\nconst {var_names[i+1]} = "
        else:
            end_marker = "\nconst records = [];"
        start_idx = html.index(start_marker)
        end_idx = html.index(end_marker, start_idx)
        html = html[:start_idx] + f"{start_marker}{payload}" + html[end_idx:]
        print(f'  injected {var_name} ({len(payload)} chars)')

    # keep the dashboard's internal "today" in sync with the actual current date
    today = datetime.now(ZoneInfo('America/Los_Angeles'))
    old_today_line_start = html.index("const TODAY_DATE = new Date(")
    old_today_line_end = html.index(";", old_today_line_start)
    new_today_line = f"const TODAY_DATE = new Date({today.year}, {today.month-1}, {today.day}); // auto-updated by refresh_dashboard.py"
    html = html[:old_today_line_start] + new_today_line + html[old_today_line_end:]
    print(f'  updated TODAY_DATE to {today.strftime("%B %d, %Y")}')

    with open(DASHBOARD_FILE, 'w') as f:
        f.write(html)

    step('Done')
    print(f'{DASHBOARD_FILE} has been refreshed with current data for all 7 shops.')

if __name__ == '__main__':
    main()
