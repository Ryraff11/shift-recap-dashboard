"""Generic per-shop recap pipeline: normalize -> extract names -> compute lateness -> full records JSON."""
import csv, json, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter

exec(open('extract_names.py').read().split("results = []")[0])  # reuse name-extraction functions/constants

def levenshtein(a, b):
    if a == b: return 0
    if len(a) < len(b): a, b = b, a
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0]*len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+(ca!=cb))
        prev = cur
    return prev[-1]

NEG_ANCHORS = ['no','none','nope','na','n/a','nah']
def is_fuzzy_negative(token):
    t = token.lower().strip('!.:) ')
    if not t or len(t) > 6: return False
    return any(levenshtein(t, anchor) <= 1 for anchor in NEG_ANCHORS)

def norm_staffing(val):
    v = val.lower()
    if 'under' in v: return 'Understaffed'
    if 'over' in v: return 'Overstaffed'
    if 'just right' in v or 'perfect' in v or 'good staffing' in v: return 'Just Right'
    return 'Unclassified'

def norm_safety(val):
    v = val.strip()
    if v == '': return ('Blank', None)
    if is_fuzzy_negative(v): return ('No', None)
    vl = re.sub(r'[^a-z ]', '', v.lower()).strip()
    if vl in ('no','none','nope','na','nah',''): return ('No', None)
    return ('Flagged', v)

def is_meaningful_tardy(text):
    t = text.strip()
    if is_fuzzy_negative(t): return False
    tl = t.lower().strip('!.:) ')
    return tl != '' and tl not in {'no','none','nope','na','n/a','nothing'} and not tl.startswith('no ')

def norm_food(val):
    v = val.strip()
    if v == '': return 'Blank'
    vl = v.lower()
    if 'yes' in vl: return 'Yes'
    if 'nope' in vl or vl.startswith('no'): return 'No / In progress'
    return 'Other: ' + v

SHIFT_PATTERNS_G = [
    (re.compile(r'\b(open(ing)?|morning)\b', re.I), 'Open'),
    (re.compile(r'\bmid\b', re.I), 'Mid'),
    (re.compile(r'\b(close|closing|night)\b', re.I), 'Close'),
]
DAY_WORDS_G = re.compile(r'\b(mon|tue|wed|thu|fri|sat|sun)\w*\b', re.I)
SHIFT_WORD_G = re.compile(r'\b(open(ing)?|morning|mid|close|closing|night)\b', re.I)

def parse_shift(text):
    for pat, label in SHIFT_PATTERNS_G:
        if pat.search(text): return label
    return 'Unknown'

def parse_name_full(text):
    cut_points = [m.start() for m in re.finditer(r'[/\-\d]', text)]
    dm = DAY_WORDS_G.search(text)
    if dm: cut_points.append(dm.start())
    sm = SHIFT_WORD_G.search(text)
    if sm: cut_points.append(sm.start())
    cut = min(cut_points) if cut_points else len(text)
    name = text[:cut].strip(' -/')
    name = re.sub(r'\s+', ' ', name).strip()
    if name and name == name.lower(): name = name.title()
    return name if name else 'Unknown'

def title_name(name):
    parts = name.split()
    out = []
    for p in parts:
        if len(p) <= 3 and p.isupper(): out.append(p)
        else: out.append(p[:1].upper() + p[1:].lower())
    return ' '.join(out)

def build_shop(shop_name, csv_path, shift_cutoff, today, days=60):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    header, data = rows[0], rows[1:]
    today_index = days - 1

    def day_index_for(dt):
        return today_index - (today.date() - dt.date()).days

    out = []
    for r in data:
        ts = r[0].strip()
        if not ts: continue
        dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        di = day_index_for(dt)
        if not (0 <= di <= today_index): continue
        shift = parse_shift(r[1])
        if shift not in ('Open','Mid','Close'): continue
        name = parse_name_full(r[1])

        staffing_raw, line_times, team_player, tardy_raw = r[3], r[2], r[4], r[5]
        safety_raw, xbro, food_inv_raw, comments = r[6], r[7], r[8], r[9]
        closing_verifone = r[10] if len(r) > 10 else ''

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)
        food_inventory = norm_food(food_inv_raw)

        cutoff_h, cutoff_m = shift_cutoff[shift]
        is_late = (dt.hour, dt.minute) > (cutoff_h, cutoff_m)

        flags = []
        if staffing == 'Understaffed':
            flags.append({'kind':'bad','employee':None,'text':'Shift reported understaffed.'})
        tp = team_player.strip()
        if tp and tp.lower() not in ('n/a','na','no'):
            flags.append({'kind':'good','employee':None,'text':tp})
        if is_meaningful_tardy(tardy_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Tardy/early-out note: {tardy_raw.strip()}'})
        if safety_status == 'Flagged':
            flags.append({'kind':'bad','employee':None,'text':f'Hazard reported: {safety_detail}'})
        xbro_s = xbro.strip()
        if xbro_s and re.search(r'struggl|coach|didn|did not|couldn', xbro_s, re.I):
            flags.append({'kind':'bad','employee':None,'text':xbro_s})
        comment = comments.strip()
        if comment:
            is_bad = bool(re.search(r'rough|slam|short staff|struggl|behind|disorganiz|heated|upset', comment, re.I))
            flags.append({'kind':'bad' if is_bad else 'good','employee':None,'text':comment})
        if is_late:
            flags.append({'kind':'bad','employee':None,'text':f'Recap submitted late — arrived {dt.strftime("%-I:%M %p")}, after the {cutoff_h:02d}:{cutoff_m:02d} grace-period cutoff for {shift}.'})

        full_recap = {
            'staffing': staffing_raw, 'lineTimes': line_times, 'teamPlayer': team_player,
            'tardy': tardy_raw, 'foodInventory': food_inventory, 'safety': safety_raw,
            'xbro': xbro, 'comments': comments, 'closingVerifone': closing_verifone,
            'closingChecklist': '',
        }

        mentions = []
        for nm in extract_leading_names(team_player): mentions.append((nm, 'good', team_player))
        for nm in extract_possessive(comments): mentions.append((nm, 'good', comments))
        for nm in extract_shoutout(comments): mentions.append((nm, 'good', comments))
        for nm in extract_tardy_names(tardy_raw): mentions.append((nm, 'bad', tardy_raw))
        for nm in extract_xbro_coach_names(xbro): mentions.append((nm, 'bad', xbro))

        seen, named_mentions = set(), []
        for nm, sentiment, src in mentions:
            canon = title_name(nm)
            key = (canon.lower(), sentiment)
            if key in seen: continue
            seen.add(key)
            named_mentions.append({'name': canon, 'kind': sentiment, 'source': src.strip()[:160]})

        out.append({
            'shop': shop_name, 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comment if comment else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
    records = build_shop(
        'Fair Oaks', 'fairoaks_recap_raw.csv',
        {'Open': (12,15), 'Mid': (17,45), 'Close': (23,35)},
        TODAY
    )
    with open('fairoaks_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} Fair Oaks records built')
    late_count = sum(1 for r in records if r['isLate'])
    print(f'{late_count} of {len(records)} submitted late')
    total_mentions = sum(len(r['namedMentions']) for r in records)
    print(f'{total_mentions} total named mentions')
    flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
    print(f'{flagged_hazards} recaps with a real flagged hazard')
