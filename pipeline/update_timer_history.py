"""
Accumulates HME timer data into a persistent history file (hme_timer_history.json),
then injects the current 60-day window's worth of it into the dashboard HTML.

Unlike the recap pipeline, this does NOT regenerate from scratch each run --
each HME email is the only record of that day that will ever exist, so today's
newly-parsed data gets ADDED to history, never overwriting prior days.

USAGE (each scheduled run):
  1. Clear stale raw inputs so coverage reflects THIS run:
       rm -f hme_*.txt hme_*.none
  2. Save each new HME "Other - Day Report" as its expected file (see HME_SHOPS in
     parse_hme_email.py): hme_175.txt (Mad), hme_2008.txt (Lichen), hme_280.txt
     (Manz), hme_207.txt (Fair Oaks), hme_pdf_181.txt (Auburn), etc.
  3. For any shop that genuinely has NO report today (after actually checking),
     write an empty marker so it reads as "checked, quiet" instead of a silent
     gap:  touch hme_280.none   (or hme_pdf_<store>.none for the PDF shops)
  4. Run: python3 update_timer_history.py  — read the HME COVERAGE report it prints.

COVERAGE: the run is cross-checked against the canonical HME_SHOPS list. Any
expected shop with neither a parsed report nor a .none marker is a SILENT FETCH
GAP and is flagged loudly (see run_coverage_report) — that is the failure this
guards against, where a shop that was never fetched looks identical to a shop
that genuinely had no data.
"""
import json, os, glob
from datetime import datetime
from zoneinfo import ZoneInfo
from parse_hme_email import parse_hme_report, HME_SHOPS, input_basename, none_basename

STALE_DAYS = 3  # a report file present this run but covering a day older than this
                # is treated as a leftover/stale input and flagged, not trusted as fresh

HISTORY_FILE = 'hme_timer_history.json'
DASHBOARD_FILE = 'shift-recap-dashboard.html'
DAYS = 60  # matches the dashboard's 60-day data window (days=60 in the template)

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def ingest_new_emails(history):
    """Parse every hme_*.txt present and add new (shop, day) rows to history.
    Returns (added, ingested, parse_failures):
      added          -- ['Shop / YYYY-MM-DD', ...] for the run summary
      ingested       -- {shop: {'date':..., 'file':...}} for the coverage check
      parse_failures -- {file: reason} for files that were present but unusable
    """
    added, ingested, parse_failures = [], {}, {}
    for txt_file in sorted(glob.glob('hme_*.txt')):
        with open(txt_file) as f:
            text = f.read()
        result = parse_hme_report(text)
        if not result:
            print(f'  SKIP {txt_file}: could not parse')
            parse_failures[txt_file] = 'not a recognizable HME report'
            continue
        if 'error' in result:
            print(f'  ERROR {txt_file}: {result["error"]}')
            parse_failures[txt_file] = result['error']
            continue
        shop = result['shop']
        date = result['date']
        history.setdefault(shop, {})
        history[shop][date] = {
            'laneTotalSec': result['lane1_avg_sec'],
            'laneTotal2Sec': result['lane2_avg_sec'],
            'totalCars': result['total_cars'],
            'window': result.get('window'),
        }
        added.append(f'{shop} / {date}')
        ingested[shop] = {'date': date, 'file': txt_file}
    return added, ingested, parse_failures


def run_coverage_report(ingested, parse_failures):
    """Cross-check this run against the canonical HME_SHOPS list and print an
    authoritative, impossible-to-miss coverage report. Returns the list of
    problem entries (unverified gaps + stale + parse failures) so the caller can
    signal them; genuine quiet days (marked with a .none file) are NOT problems.
    """
    today = datetime.now(ZoneInfo('America/Los_Angeles')).date()
    reported, quiet, gaps, stale, errored = [], [], [], [], []

    for e in HME_SHOPS:
        shop = e['shop']
        if shop in ingested:
            d = ingested[shop]['date']
            try:
                age = (today - datetime.strptime(d, '%Y-%m-%d').date()).days
            except ValueError:
                age = None
            if age is not None and age > STALE_DAYS:
                stale.append((e, d, age))
            else:
                reported.append((e, d))
        elif input_basename(e) in parse_failures:
            errored.append((e, parse_failures[input_basename(e)]))
        elif os.path.exists(none_basename(e)):
            quiet.append(e)
        else:
            gaps.append(e)

    n = len(HME_SHOPS)
    accounted = len(reported) + len(quiet)
    print('\n--- HME COVERAGE (canonical HME_SHOPS = %d expected) ---' % n)
    for e, d in reported:
        print(f'  OK       {e["shop"]:<10} ({input_basename(e)}) -> {d}')
    for e in quiet:
        print(f'  quiet    {e["shop"]:<10} ({none_basename(e)}) -> no report today (confirmed checked)')
    for e, d, age in stale:
        print(f'  ! STALE  {e["shop"]:<10} ({input_basename(e)}) -> {d} is {age}d old — leftover input, not a fresh fetch')
    for e, reason in errored:
        print(f'  ! ERROR  {e["shop"]:<10} ({input_basename(e)}) -> present but unparseable: {reason}')
    for e in gaps:
        print(f'  ! GAP    {e["shop"]:<10} -> NO report and NO .none marker')

    problems = [('GAP', e) for e in gaps] + [('STALE', e) for e, _, _ in stale] + [('ERROR', e) for e, _ in errored]
    if problems:
        bar = '=' * 66
        print('\n' + bar)
        print('  !!  HME COVERAGE ALERT — %d of %d expected shop(s) NOT verified this run.' % (len(problems), n))
        print('      A GAP means the shop was neither reported nor marked checked —')
        print('      indistinguishable from a fetch that never happened. Do NOT treat')
        print('      today\'s data as complete until each is resolved:')
        for kind, e in problems:
            if kind == 'GAP':
                fix = f'fetch {e["locator"]}  OR (if truly no report) touch {none_basename(e)}'
            elif kind == 'STALE':
                fix = f're-fetch {e["locator"]} — the file on disk is a leftover from a prior run'
            else:
                fix = f're-fetch {e["locator"]} — the saved file did not parse'
            print(f'        - {e["shop"]} (#{e["store"]}, {kind}): {fix}')
        print(bar)
    else:
        print('  coverage: %d/%d expected shops accounted for (%d reported, %d confirmed-quiet). OK'
              % (accounted, n, len(reported), len(quiet)))
    return problems

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
    added, ingested, parse_failures = ingest_new_emails(history)
    if added:
        print(f'Added {len(added)} new day(s) of timer data:')
        for a in added:
            print(f'  {a}')
    else:
        print('No new hme_*.txt files found to ingest.')
    save_history(history)

    real_timer_js = build_real_timer_js(history)
    inject_into_dashboard(real_timer_js)
    print(f'Dashboard updated with current {DAYS}-day timer window.')

    for shop, by_idx in real_timer_js.items():
        print(f'  {shop}: {len(by_idx)} real day(s) in current window')

    # Authoritative per-run coverage vs the canonical HME_SHOPS list. This is what
    # makes a silent fetch gap impossible: a shop that was never fetched (no file,
    # no .none marker) is flagged loudly instead of vanishing into a zero.
    run_coverage_report(ingested, parse_failures)

if __name__ == '__main__':
    main()
