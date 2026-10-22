"""Row files for the private Daily Shop Pulse artifact (the Claude dashboard).

Reads the pipeline outputs that already exist and writes flat JSON arrays:
  data/pulse_rows.json      one row per shop, day and shift (from data/pulse.json)
  data/timer_rows.json      one row per shop and day, last 14 days (from pipeline/hme_timer_history.json)
  pipeline/brew_rows.json   one row per Weekly Brew item WITH details (from pipeline/brew_full.json,
                            only when that gitignored file exists)

Usage (from the repo root):  python3 pipeline/pulse_rows.py
The refresh routine uploads these three files to the artifact (ROUTINE_PROMPT.txt, STEP 5b).
"""
import json, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)


def pulse_rows():
    p = json.load(open(P('data', 'pulse.json')))
    rows = []
    for d in p['days']:
        for shop in p['shops']:
            for sh in p['shifts']:
                s = (d['shops'].get(shop) or {}).get(sh)
                if not s:
                    continue
                recs = s.get('recaps') or []
                r0 = recs[0] if recs else {}
                flags = [f for r in recs for f in (r.get('flags') or [])]
                haz = [f['text'].split(':', 1)[1].strip() for f in flags
                       if (f.get('text') or '').lower().startswith('hazard reported')]
                rows.append({
                    'date': d['date'], 'shop': shop, 'shift': sh, 'status': s.get('status'),
                    'lead': s.get('scheduledLead') or '', 'by': r0.get('submittedBy') or '',
                    'at': (r0.get('submittedAt') or '')[:16].replace('T', ' '),
                    'late': 'yes' if any(r.get('late') for r in recs) else '',
                    'good': sum(1 for f in flags if f.get('kind') == 'good'),
                    'bad': sum(1 for f in flags if f.get('kind') == 'bad'),
                    'hazards': ' | '.join(haz),
                })
    return rows


def timer_rows(days=14):
    t = json.load(open(P('pipeline', 'hme_timer_history.json')))
    cut = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = [{'shop': shop, 'date': day, 'laneTotalSec': v.get('laneTotalSec'),
             'totalCars': v.get('totalCars'), 'window': v.get('window') or ''}
            for shop, by_day in t.items() for day, v in by_day.items()
            if day >= cut and v.get('laneTotalSec') is not None]
    rows.sort(key=lambda r: (r['date'], r['shop']))
    return rows


def brew_rows():
    src = P('pipeline', 'brew_full.json')
    if not os.path.exists(src):
        return None
    b = json.load(open(src))
    return [{'date': i['date'], 'end': i.get('end', ''), 'title': i['title'], 'kind': i.get('kind', ''),
             'details': '\n'.join(i.get('details', [])), 'source': b.get('source', '')} for i in b['items']]


if __name__ == '__main__':
    r = pulse_rows(); json.dump(r, open(P('data', 'pulse_rows.json'), 'w'), indent=0)
    print('wrote data/pulse_rows.json', len(r), 'rows')
    r = timer_rows(); json.dump(r, open(P('data', 'timer_rows.json'), 'w'), indent=0)
    print('wrote data/timer_rows.json', len(r), 'rows')
    r = brew_rows()
    if r is None:
        print('no pipeline/brew_full.json — brew_rows.json not written (artifact keeps its last Brew)')
    else:
        json.dump(r, open(P('pipeline', 'brew_rows.json'), 'w'), indent=0)
        print('wrote pipeline/brew_rows.json', len(r), 'rows')
