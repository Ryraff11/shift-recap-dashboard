"""Rows for the "Daily Shop Pulse feed" Google Sheet, from data/pulse.json.

One row per shop per shift per day (newest day first). Statuses cover all 7 days;
the free-text payloads (flags, answers) are kept only for the newest FULL_TEXT_DAYS
days so the sheet refresh stays small. Prints a JSON 2-D array (header row first)
ready for the Google Sheets update_values tool.

Usage (from the repo root):  python3 pipeline/pulse_sheet_rows.py > /tmp/rows.json
"""
import json, sys, os

FULL_TEXT_DAYS = 2
COLS = ['date', 'shop', 'shift', 'status', 'lead', 'by', 'at', 'late', 'recapCount',
        'good', 'bad', 'hazards', 'flags', 'answers', 'generatedAt']

def rows_from_pulse(pulse):
    rows = [COLS]
    for di, day in enumerate(pulse['days']):
        full = di < FULL_TEXT_DAYS
        for shop, slots in day['shops'].items():
            for sh in ('Open', 'Mid', 'Close'):
                s = slots.get(sh) or {}
                recs = s.get('recaps') or []
                r0 = recs[0] if recs else {}
                flags = [f for r in recs for f in (r.get('flags') or [])]
                rows.append([
                    day['date'], shop, sh, s.get('status') or 'missing', s.get('scheduledLead') or '',
                    r0.get('submittedBy') or '', r0.get('submittedAt') or '', 'TRUE' if r0.get('late') else 'FALSE',
                    len(recs),
                    sum(1 for f in flags if f.get('kind') == 'good'),
                    sum(1 for f in flags if f.get('kind') == 'bad'),
                    sum(1 for f in flags if (f.get('text') or '').startswith('Hazard reported')),
                    json.dumps(flags, ensure_ascii=False) if full else '',
                    json.dumps(r0.get('answers') or {}, ensure_ascii=False) if full else '',
                    pulse.get('generatedAt') or '',
                ])
    return rows

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, '..', 'data', 'pulse.json')
    with open(src, encoding='utf-8') as f:
        rows = rows_from_pulse(json.load(f))
    json.dump(rows, sys.stdout, ensure_ascii=False, separators=(',', ':'))
