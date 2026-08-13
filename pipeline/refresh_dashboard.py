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
  Optionally place deputy_schedule_raw.csv (exported from the Deputy shift-lead sheet)
  to refresh the scheduled-lead names shown on missing/late recaps; if it's absent the
  existing schedule already baked into the dashboard is left untouched.
  Then run:  python3 refresh_dashboard.py
  It overwrites shift-recap-dashboard.html with fresh data for all 7 shops.
"""
import csv, json, subprocess, sys
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

    # PRIVACY: index.html is committed to a PUBLIC repo, so recap records are scrubbed
    # to "First L." at this choke point (covers every shop regardless of build-script
    # quirks). Structured name fields are truncated unconditionally; free-text fields
    # (flag text, mention sources, fullRecap answers) get exact word-boundary
    # replacement of the known filer roster only, so ordinary prose isn't mangled.
    def _privacy_name(full):
        parts = full.split()
        if len(parts) < 2:
            return full
        return f'{parts[0]} {parts[-1][0]}.'

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
    # load all shops, harvest the name roster, scrub names, then inject.
    # Roster = every filer name (reliable: comes from the form's name field) plus
    # mention names that are SHAPED like a real person name. Mention extraction
    # produces junk phrases too ("Aiden Kicked Butt", "Definitely Gabe") — replacing
    # those in prose would mangle sentences without protecting anyone, so a mention
    # only joins the roster when both tokens look like name tokens.
    import re as _re
    _STOP = {
        'both','always','girl','boy','everybody','everyone','generally','really','think','thought',
        'probably','definitely','def','okay','just','lil','thin','homes','came','kicked','stayed',
        'honestly','whole','crew','team','player','best','trainee','from','would','say','doing',
        'extra','butt','since','because','omg','umm','our','my','so','productive','multitasked',
        'and','the','was','is','are','been','being','of','to','too','again','today','tonight',
        'helped','went','got','said','did','has','had','were','not','but','for','with','all',
    }
    def _norm_tok(t):
        return _re.sub(r'(.)\1{2,}', r'\1', t.lower())  # 'Reeeeally' -> 'really'
    def _looks_like_person(nm):
        toks = nm.split()
        if len(toks) != 2:
            return False
        return all(t.isalpha() and len(t) >= 3 and _norm_tok(t) not in _STOP for t in toks)
    def _mention_name_prefix(nm):
        """Return the scrub-worthy name inside a mention, or None.
        2 tokens: the name itself if person-shaped. 3 tokens where the last is a
        filler word ('Maddie Watts Doing'): the leading 2-token name."""
        toks = nm.split()
        if len(toks) == 2 and _looks_like_person(nm):
            return nm
        if len(toks) == 3 and _looks_like_person(' '.join(toks[:2])) and _norm_tok(toks[2]) in _STOP:
            return ' '.join(toks[:2])
        return None

    shop_records = {}
    _roster = set()
    for var_name, jf in shop_files.items():
        with open(jf) as f:
            shop_records[var_name] = json.load(f)
        for r in shop_records[var_name]:
            emp = (r.get('employee') or '').strip()
            if len(emp.split()) >= 2:
                _roster.add(emp)
            for m in r.get('namedMentions') or []:
                cand = _mention_name_prefix((m.get('name') or '').strip())
                if cand:
                    _roster.add(cand)
    _patterns = [(_re.compile(r'\b' + _re.escape(n) + r'\b', _re.IGNORECASE), _privacy_name(n))
                 for n in sorted(_roster, key=len, reverse=True)]

    def _scrub_text(s):
        for pat, short in _patterns:
            s = pat.sub(short, s)
        return s

    _n_names, _n_prose = 0, 0
    for recs in shop_records.values():
        for r in recs:
            emp = r.get('employee') or ''
            if len(emp.split()) >= 2:
                r['employee'] = _privacy_name(emp)
                _n_names += 1
            for m in r.get('namedMentions') or []:
                nm = m.get('name') or ''
                if len(nm.split()) >= 2:
                    m['name'] = _privacy_name(nm)
                    _n_names += 1
                if m.get('source'):
                    _new = _scrub_text(m['source'])
                    if _new != m['source']:
                        m['source'] = _new
                        _n_prose += 1
            for fl in r.get('flags') or []:
                fe = fl.get('employee') or ''
                if len(fe.split()) >= 2:
                    fl['employee'] = _privacy_name(fe)
                    _n_names += 1
                if fl.get('text'):
                    _new = _scrub_text(fl['text'])
                    if _new != fl['text']:
                        fl['text'] = _new
                        _n_prose += 1
            fr = r.get('fullRecap') or {}
            for k, v in list(fr.items()):
                if isinstance(v, str) and v:
                    _new = _scrub_text(v)
                    if _new != v:
                        fr[k] = _new
                        _n_prose += 1
    print(f'  privacy: shortened {_n_names} structured name(s), scrubbed {_n_prose} free-text field(s) '
          f'(roster of {len(_roster)} full name(s))')

    var_names = list(shop_files.keys())
    for i, var_name in enumerate(var_names):
        payload = json.dumps(shop_records[var_name], indent=2)
        start_marker = f"const {var_name} = "
        if i + 1 < len(var_names):
            end_marker = f"\nconst {var_names[i+1]} = "
        else:
            end_marker = "\nconst records = [];"
        start_idx = html.index(start_marker)
        end_idx = html.index(end_marker, start_idx)
        html = html[:start_idx] + f"{start_marker}{payload}" + html[end_idx:]
        print(f'  injected {var_name} ({len(payload)} chars)')

    # inject real HME drive-thru timer history (empty {} if hme_timer_history.json isn't present yet).
    # update_timer_history.py owns this file and re-injects fresher data after the recap build;
    # reading it here keeps the build self-consistent even if the HME step is skipped this run.
    timer = {}
    if os.path.exists('hme_timer_history.json'):
        with open('hme_timer_history.json') as f:
            timer = json.load(f)
    t_start = html.index("const REAL_TIMER_DATA = ")
    t_end = html.index(";", t_start)
    html = html[:t_start] + f"const REAL_TIMER_DATA = {json.dumps(timer)}" + html[t_end:]
    print(f'  injected REAL_TIMER_DATA ({len(timer)} shop(s), {sum(len(v) for v in timer.values())} shop-day(s))')

    # Deputy shift-lead schedule. Exported from the Deputy sheet as deputy_schedule_raw.csv
    # (Date, Shop, ShiftLabel, EmployeeName, EmployeeId, IsEmptySlot, ScheduledStart, ScheduledEnd).
    # Accumulated the same way as the HME timer data: each run MERGES the export into the
    # persistent deputy_schedule_history.json and NEVER shrinks it, so the schedule survives
    # even though the sheet itself only keeps a couple of recent days. A trailing window of
    # that history is then injected as REAL_DEPUTY_SCHEDULE for the client to read.
    #
    # Keys: a row with a real Open/Mid/Close ShiftLabel uses "YYYY-MM-DD|Shop|ShiftLabel" —
    # the exact key the client looks up. A row with a BLANK ShiftLabel (Deputy's safety
    # behavior when a shop's leads don't map cleanly onto 3 dayparts, e.g. 4 overlapping
    # leads) is NOT a daypart, so it gets a collision-proof key "YYYY-MM-DD|Shop|#<EmployeeId>"
    # instead of silently overwriting sibling rows. Those are preserved in history for the
    # record but are NOT injected — they have no Open/Mid/Close slot to display.
    DEPUTY_HISTORY_FILE = 'deputy_schedule_history.json'
    DEPUTY_WINDOW_DAYS = 45
    # _privacy_name (defined above, at the recap injection step) applies here too:
    # this history file is committed to the public repo, so a full surname tied to
    # a work schedule must never be stored — 'Myah Newton' -> 'Myah N.'.
    deputy_hist = {}
    if os.path.exists(DEPUTY_HISTORY_FILE):
        with open(DEPUTY_HISTORY_FILE) as f:
            deputy_hist = json.load(f)
    # Self-heal entries written before the privacy rule existed, and persist the
    # scrub even on runs where no fresh CSV export is present.
    _scrubbed = 0
    for _v in deputy_hist.values():
        _lead = _v.get('lead')
        if _lead:
            _short = _privacy_name(_lead)
            if _short != _lead:
                _v['lead'] = _short
                _scrubbed += 1
    if _scrubbed:
        with open(DEPUTY_HISTORY_FILE, 'w') as f:
            json.dump(deputy_hist, f, indent=2, sort_keys=True)
        print(f'  privacy: shortened {_scrubbed} pre-existing full name(s) in deputy history')
    if os.path.exists('deputy_schedule_raw.csv'):
        merged, unlabeled = 0, 0
        with open('deputy_schedule_raw.csv', newline='', encoding='utf-8-sig') as f:
            for i, row in enumerate(csv.DictReader(f)):
                date = (row.get('Date') or '').strip()
                shop = (row.get('Shop') or '').strip()
                shift = (row.get('ShiftLabel') or '').strip()
                if not (date and shop):
                    continue
                empty = (row.get('IsEmptySlot') or '').strip().upper() == 'TRUE'
                # truncate at the ingest boundary so a full name never reaches the
                # committed JSON — neither in 'lead' nor embedded in an unlabeled key
                name = _privacy_name((row.get('EmployeeName') or '').strip())
                emp_id = (row.get('EmployeeId') or '').strip()
                if shift in ('Open', 'Mid', 'Close'):
                    key = f'{date}|{shop}|{shift}'
                else:
                    unlabeled += 1
                    # collision-proof: unlabeled/overlapping leads keyed by roster id so they
                    # never overwrite each other (they simply won't render as a daypart).
                    key = f'{date}|{shop}|#{emp_id or name or i}'
                deputy_hist[key] = {
                    'lead': (None if empty or not name else name),
                    'empty': empty,
                    'shift': shift,
                    'id': emp_id,
                }
                merged += 1
        with open(DEPUTY_HISTORY_FILE, 'w') as f:
            json.dump(deputy_hist, f, indent=2, sort_keys=True)
        print(f'  merged deputy schedule: {merged} row(s) this run ({unlabeled} unlabeled), '
              f'{len(deputy_hist)} total in history')
    else:
        print('  deputy_schedule_raw.csv not present — using existing deputy_schedule_history.json as-is')

    # Inject a trailing window of RESOLVED (Open/Mid/Close) slots as REAL_DEPUTY_SCHEDULE,
    # keyed exactly as the client reads it. Unlabeled (#id) keys stay in history but out of
    # the injected payload since they have no daypart to render.
    _dep_today = datetime.now(ZoneInfo('America/Los_Angeles')).date()
    def _dep_in_window(ds):
        try:
            delta = (_dep_today - datetime.strptime(ds, '%Y-%m-%d').date()).days
        except ValueError:
            return False
        return 0 <= delta <= DEPUTY_WINDOW_DAYS - 1
    deputy_inject = {}
    for key, v in deputy_hist.items():
        parts = key.split('|')
        if len(parts) != 3 or parts[2].startswith('#'):
            continue
        if _dep_in_window(parts[0]):
            deputy_inject[key] = {'lead': v.get('lead'), 'empty': bool(v.get('empty'))}
    # Only inject if the template actually declares the marker. A template that
    # doesn't render the deputy schedule (e.g. the masthead/grid rebuild) simply
    # has no "const REAL_DEPUTY_SCHEDULE = " to write into -- skip gracefully
    # rather than crashing the whole build. The history above is still updated.
    _dep_marker = "const REAL_DEPUTY_SCHEDULE = "
    if _dep_marker in html:
        d_start = html.index(_dep_marker)
        d_end = html.index(";", d_start)
        html = html[:d_start] + f"const REAL_DEPUTY_SCHEDULE = {json.dumps(deputy_inject)}" + html[d_end:]
        empties = sum(1 for x in deputy_inject.values() if x['empty'])
        print(f'  injected REAL_DEPUTY_SCHEDULE ({len(deputy_inject)} slot(s) in last {DEPUTY_WINDOW_DAYS}d, {empties} empty)')
    else:
        print('  SKIP REAL_DEPUTY_SCHEDULE injection — template has no deputy marker (feature not in this template); history still updated')

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
