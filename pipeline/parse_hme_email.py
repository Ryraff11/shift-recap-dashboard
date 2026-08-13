"""Parses one HME ZOOM day report into structured data.

Two source formats are auto-detected:
  - PLAIN-TEXT email body  ("HME ZOOM: Other #<num> - Day Report"): Mad #175,
    Lichen #2008, Manz #280, Fair Oaks #207 (sent under the old nickname "K Town").
  - PDF-EXTRACTED text      ("Day Summary Report", header "Restaurant #<num> <Name>"):
    Auburn #000181, Antelope #4341, OV/Orangevale #2011, Fireside #2015. These are
    auto-saved to the "HME Reports" Drive folder; the scheduled run pulls the extracted
    text via Drive's read_file_content and saves it as hme_pdf_<num>.txt.

parse_hme_report(text) auto-detects the format and returns a dict:
  {shop, store_num, date, lane1_avg_sec, lane1_cars, lane2_avg_sec, lane2_cars, total_cars, window}
where `window` is the report's coverage span (e.g. '5:00a-11:00p'), read from the From:/To:
lines (plain-text) or the Range line (PDF), or None if the times can't be read.
Returns {'error': ...} when the store/date/lane can't be read, or None if it isn't a report.
"""
import re
from datetime import datetime

# ── CANONICAL HME SHOP REGISTRY ─────────────────────────────────────────────
# The SINGLE SOURCE OF TRUTH for which shops the HME timer pipeline expects each
# run and how each report is fetched. STORE_MAP (below), the per-run coverage
# check in update_timer_history.py, and the scheduled run's fetch list all
# derive from THIS list — so a shop can never silently fall out of sync: add or
# remove one here and the coverage check immediately expects the change (an
# un-fetched shop then shows up as a loud gap instead of a silent zero).
#   source 'text' -> Gmail plain-text "Other - Day Report", saved as hme_<store>.txt
#   source 'pdf'  -> Drive "Day Summary Report" PDF text,    saved as hme_pdf_<store>.txt
HME_SHOPS = [
    {'store': '175',  'shop': 'Mad',       'source': 'text', 'locator': 'HME ZOOM: Other #175 - Day Report'},
    {'store': '2008', 'shop': 'Lichen',    'source': 'text', 'locator': 'HME ZOOM: Other #2008 - Day Report'},
    {'store': '280',  'shop': 'Manz',      'source': 'text', 'locator': 'HME ZOOM: Other #280 - Day Report'},
    {'store': '207',  'shop': 'Fair Oaks', 'source': 'text', 'locator': 'HME ZOOM: Other #207 - Day Report'},  # old nickname "K Town"
    {'store': '181',  'shop': 'Auburn',    'source': 'pdf',  'locator': 'title contains "000181"'},
    {'store': '4341', 'shop': 'Antelope',  'source': 'pdf',  'locator': 'title contains "4341"'},
    {'store': '2011', 'shop': 'OV',        'source': 'pdf',  'locator': 'title contains "2011"'},
    {'store': '2015', 'shop': 'Fireside',  'source': 'pdf',  'locator': 'title contains "2015"'},
]

# Derived downstream — do NOT hand-maintain a second copy.
STORE_MAP = {e['store']: e['shop'] for e in HME_SHOPS}

def input_basename(entry):
    """The gitignored raw-input filename the run writes for this shop's report."""
    return f"hme_pdf_{entry['store']}.txt" if entry['source'] == 'pdf' else f"hme_{entry['store']}.txt"

def none_basename(entry):
    """Marker the run writes to record 'checked, genuinely no report today' —
    the signal that separates a real quiet day from a silent fetch miss."""
    return f"hme_pdf_{entry['store']}.none" if entry['source'] == 'pdf' else f"hme_{entry['store']}.none"

def shop_for_store(store_num):
    return STORE_MAP.get(store_num) or STORE_MAP.get(store_num.lstrip('0'))

def sec_from_mmss(mmss):
    m, s = mmss.split(':')
    return int(m) * 60 + int(s)

def _fmt_clock(h24, mnt):
    ap = 'a' if h24 < 12 else 'p'
    hh = h24 % 12 or 12
    return f'{hh}:{mnt:02d}{ap}'

def _clock24(h12, mnt, ap):
    h = int(h12) % 12
    if ap.upper().startswith('P'):
        h += 12
    return (h, int(mnt))

def _window_label(start, end):
    """Human window string for the report's coverage, e.g. '5:00a-11:00p'. An end
    minute of :59 is the report closing one minute shy of the hour, so it rounds up
    for display (10:59p -> 11:00p) -- EXCEPT when rounding would land exactly on the
    start time (the 24-hour overnight reports, From 5:00A to 4:59A next day), where
    the literal 4:59a is kept so the overnight span stays visible instead of reading
    '5:00a-5:00a'. Returns None only when a caller passes no times."""
    eh, em = end
    if em == 59:
        reh, rem = (eh + 1) % 24, 0
        if (reh, rem) != tuple(start):
            eh, em = reh, rem
    return f'{_fmt_clock(*start)}–{_fmt_clock(eh, em)}'

def _looks_like_pdf(text):
    """The PDF ('Day Summary Report') format is headed by 'Restaurant #<num> <Name>';
    the plain-text email uses 'Store # : <num>'. Detect the PDF shape so both can share
    one entry point."""
    return ('Day Summary Report' in text) or bool(re.search(r'Restaurant\s*\\?#', text))

def _parse_pdf_summary(text):
    """Parse the PDF-extracted 'Day Summary Report' text (Auburn/Antelope/OV/Fireside).

    The extraction is tolerant of two layouts seen in practice: values inline with their
    label ('Lane Total 620 01:17') and values on their own lines ('Lane Total\\n\\n796\\n\\n01:04'),
    so every field is matched with \\s+ (which spans the blank-line separators). The store
    number may be markdown-escaped ('Restaurant \\#000181') by the text extractor.

    These are single-lane stores: the report's 'Lane Total 2' is a sub-metric that repeats
    the same car count, not a second physical lane, so lane2 is left null and cars are not
    doubled -- keeping them consistent with the single-lane plain-text shops (Lichen/Manz).
    """
    sm = re.search(r'Restaurant\s*\\?#\s*0*(\d+)', text)
    if not sm:
        return None
    store_num = sm.group(1)
    shop = shop_for_store(store_num)
    if not shop:
        return {'error': f'Unknown store number {store_num} -- not in STORE_MAP, add it before this can be used'}

    # business day = the "From" side of the report range, e.g. "7/27/2026 5:00:00 AM to ..."
    # (deliberately not the "Print Date", which is when the PDF was generated).
    dm = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M\s+to\b', text)
    if not dm:
        return {'error': 'Could not find date range in PDF report'}
    report_date = datetime.strptime(dm.group(1), '%m/%d/%Y').date()

    # coverage window from the Range line, e.g.
    #   '7/27/2026 5:00:00 AM to 7/27/2026 11:00:00 PM'  ->  '5:00a-11:00p'
    # (None if the range can't be read; the dashboard then falls back to the date alone.)
    wm = re.search(r'\d{1,2}/\d{1,2}/\d{4}\s+(\d{1,2}):(\d{2}):\d{2}\s*([AP])M?\s+to\s+'
                   r'\d{1,2}/\d{1,2}/\d{4}\s+(\d{1,2}):(\d{2}):\d{2}\s*([AP])M?', text)
    window = _window_label(_clock24(*wm.groups()[:3]), _clock24(*wm.groups()[3:])) if wm else None

    lm = re.search(r'Lane Total\s+(\d+)\s+(\d{1,2}:\d{2})', text)
    if not lm:
        return {'error': 'Could not find Lane Total in PDF report'}
    cars = int(lm.group(1))
    avg_sec = sec_from_mmss(lm.group(2))

    return {
        'shop': shop,
        'store_num': store_num,
        'date': report_date.isoformat(),
        'lane1_avg_sec': avg_sec,
        'lane1_cars': cars,
        'lane2_avg_sec': None,
        'lane2_cars': None,
        'total_cars': cars,
        'window': window,
    }

def parse_hme_report(text):
    # PDF "Day Summary Report" (Auburn/Antelope/OV/Fireside) -- different layout entirely.
    if _looks_like_pdf(text):
        return _parse_pdf_summary(text)

    # plain-text "Other - Day Report" (Mad/Lichen/Manz/Fair Oaks)
    store_match = re.search(r'Store #\s*:\s*(\d+)', text)
    if not store_match:
        return None
    store_num = store_match.group(1)
    shop = STORE_MAP.get(store_num)
    if not shop:
        return {'error': f'Unknown store number {store_num} -- not in STORE_MAP, add it before this can be used'}

    from_match = re.search(r'From:\s*\w+\s+(\d{2}/\d{2}/\d{2})', text)
    if not from_match:
        return {'error': 'Could not find From: date in report'}
    report_date = datetime.strptime(from_match.group(1), '%m/%d/%y').date()

    # coverage window from the From:/To: lines, e.g.
    #   'From:SAT 08/08/26 05:00A' / 'To :SAT 08/08/26 10:59P'  ->  '5:00a-11:00p'
    # (None if either clock is missing; the dashboard then falls back to the date alone.)
    wf = re.search(r'From:\s*\w+\s+\d{2}/\d{2}/\d{2}\s+(\d{1,2}):(\d{2})\s*([AP])', text)
    wt = re.search(r'To\s*:\s*\w+\s+\d{2}/\d{2}/\d{2}\s+(\d{1,2}):(\d{2})\s*([AP])', text)
    window = _window_label(_clock24(*wf.groups()), _clock24(*wt.groups())) if wf and wt else None

    def extract_section(label):
        m = re.search(rf'{re.escape(label)}\s*\n-+\nAverage Time = (\d+:\d+)\nTotal Cars = (\d+)', text)
        if not m:
            return None
        return {'avg_sec': sec_from_mmss(m.group(1)), 'cars': int(m.group(2))}

    lane1 = extract_section('Lane 1 Total') or extract_section('Lane Total')
    lane2 = extract_section('Lane 2 Total')

    # a shop is genuinely double-sided only if Lane 2 exists AND differs from Lane 1
    # (single-lane reports repeat identical numbers under "Lane Total 2", which is not a second lane)
    is_double = lane2 is not None and lane2 != lane1

    return {
        'shop': shop,
        'store_num': store_num,
        'date': report_date.isoformat(),
        'lane1_avg_sec': lane1['avg_sec'] if lane1 else None,
        'lane1_cars': lane1['cars'] if lane1 else None,
        'lane2_avg_sec': lane2['avg_sec'] if is_double else None,
        'lane2_cars': lane2['cars'] if is_double else None,
        'total_cars': (lane1['cars'] if lane1 else 0) + (lane2['cars'] if is_double else 0),
        'window': window,
    }

if __name__ == '__main__':
    import sys, json
    with open(sys.argv[1]) as f:
        text = f.read()
    result = parse_hme_report(text)
    print(json.dumps(result, indent=2))
