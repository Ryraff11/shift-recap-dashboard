"""Parses one HME ZOOM day report into structured data.

Two source formats are auto-detected:
  - PLAIN-TEXT email body  ("HME ZOOM: Other #<num> - Day Report"): Mad #175,
    Lichen #2008, Manz #280, Fair Oaks #207 (sent under the old nickname "K Town").
  - PDF-EXTRACTED text      ("Day Summary Report", header "Restaurant #<num> <Name>"):
    Auburn #000181, Antelope #4341, OV/Orangevale #2011, Fireside #2015. These are
    auto-saved to the "HME Reports" Drive folder; the scheduled run pulls the extracted
    text via Drive's read_file_content and saves it as hme_pdf_<num>.txt.

parse_hme_report(text) auto-detects the format and returns a dict:
  {shop, store_num, date, lane1_avg_sec, lane1_cars, lane2_avg_sec, lane2_cars, total_cars}
or {'error': ...} when the store/date/lane can't be read, or None if it isn't a report.
"""
import re
from datetime import datetime

STORE_MAP = {
    '175': 'Mad',
    '2008': 'Lichen',
    '280': 'Manz',
    '207': 'Fair Oaks',   # sent under the old nickname "K Town"
    # PDF "Day Summary Report" stores (numbers may carry leading zeros in the header):
    '181': 'Auburn',
    '4341': 'Antelope',
    '2011': 'OV',
    '2015': 'Fireside',
}

def shop_for_store(store_num):
    return STORE_MAP.get(store_num) or STORE_MAP.get(store_num.lstrip('0'))

def sec_from_mmss(mmss):
    m, s = mmss.split(':')
    return int(m) * 60 + int(s)

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
    }

if __name__ == '__main__':
    import sys, json
    with open(sys.argv[1]) as f:
        text = f.read()
    result = parse_hme_report(text)
    print(json.dumps(result, indent=2))
