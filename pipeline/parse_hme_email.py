"""Parse HME ZOOM drive-thru timer reports.

HME emails come in two shapes, keyed by store number:
  - INLINE BODY  (subject "HME ZOOM: Other #<num> - Day Report"): the numbers are in
    the email plaintext body. Shops: MadHouse #175, Lichen #2008, Manz #280 (and
    K Town #207, which we skip). This module fully parses that format.
  - PDF ATTACHMENT (subject "HME ZOOM Nitro: Summary Day Report for <Name> #<num>"):
    the numbers are inside an attached PDF. Shops: Auburn #000181, Antelope #4341,
    OV/Orangevale #2011, Fireside #2015. The current Gmail connector can't download
    attachment bytes, so those are NOT parseable yet -- see parse_pdf_text() (stub).

parse_inline_report(body) -> dict or None:
    {store, shop, date (YYYY-MM-DD business day), laneTotalSec, laneTotal2Sec, totalCars}
"""
import re

# HME store number -> dashboard shop name. Store numbers may carry leading zeros in the
# PDF subjects (e.g. 000181); we match on both the raw and zero-stripped form.
STORE_TO_SHOP = {
    '175': 'Mad',
    '2008': 'Lichen',
    '280': 'Manz',
    '000181': 'Auburn', '181': 'Auburn',
    '4341': 'Antelope',
    '2011': 'OV',
    '2015': 'Fireside',
    # '207' = K Town: different store, not on the dashboard -> intentionally unmapped.
    # Fair Oaks: not sending HME reports yet.
}

def shop_for_store(store):
    return STORE_TO_SHOP.get(store) or STORE_TO_SHOP.get(store.lstrip('0'))

def _mmss_to_seconds(s):
    m, sec = s.split(':')
    return int(m) * 60 + int(sec)

def _extract_lane(body, header):
    """Grab 'Average Time' + 'Total Cars' from a lane section whose header line is
    exactly `header` (anchored, so 'Lane Total' won't match 'Lane Total 2')."""
    pat = re.compile(r'^' + re.escape(header) + r'\s*\n-+\nAverage Time = (\d+:\d+)\nTotal Cars = (\d+)', re.M)
    m = pat.search(body)
    if not m:
        return None
    return _mmss_to_seconds(m.group(1)), int(m.group(2))

def parse_inline_report(body):
    """Parse an inline-body HME 'Day Report'. Returns a dict or None if it can't be read
    (unknown store, or no lane section found)."""
    sm = re.search(r'Store # :\s*(\d+)', body)
    fm = re.search(r'From:\w+\s+(\d{2})/(\d{2})/(\d{2})', body)
    if not sm or not fm:
        return None
    store = sm.group(1)
    shop = shop_for_store(store)
    if not shop:
        return None  # store we don't track (e.g. K Town #207)
    mm, dd, yy = fm.groups()
    date = f'20{yy}-{mm}-{dd}'  # business day = the report's "From" date

    lane1 = _extract_lane(body, 'Lane 1 Total')
    lane2 = _extract_lane(body, 'Lane 2 Total')
    lane = _extract_lane(body, 'Lane Total')
    if lane1 and lane2:  # double-lane store (e.g. MadHouse)
        lane_total_sec, cars1 = lane1
        lane_total2_sec, cars2 = lane2
        total_cars = cars1 + cars2
    elif lane:           # single-lane store (e.g. Lichen, Manz)
        lane_total_sec, total_cars = lane
        lane_total2_sec = None
    else:
        return None

    return {
        'store': store, 'shop': shop, 'date': date,
        'laneTotalSec': lane_total_sec,
        'laneTotal2Sec': lane_total2_sec,
        'totalCars': total_cars,
    }

def parse_pdf_text(text):
    """Placeholder for the PDF (Nitro Summary) format. Not wired up: the Gmail connector
    in use can't fetch attachment bytes, so PDF-format shops (Auburn/Antelope/OV/Fireside)
    aren't available yet. If/when PDF text can be extracted, implement parsing here and
    have update_timer_history.py feed it in. Returns a list of report dicts."""
    return []

if __name__ == '__main__':
    # tiny self-test on a synthetic single-lane report
    sample = ("Day Report\n------------------------\nTUE 07/28/26 05:00:00A\n"
              "Store # : 2008\nStore Desc.: Lichen\nFrom:MON 07/27/26 05:00A\n"
              "To :TUE 07/28/26 04:59A\n\nLane Total\n-------\nAverage Time = 1:21\n"
              "Total Cars = 561\n\nLane Total 2\n-------\nAverage Time = 9:99\nTotal Cars = 0\n"
              "-----End of Report------")
    print(parse_inline_report(sample))
