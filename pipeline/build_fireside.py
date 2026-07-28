import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
exec(open('extract_names.py').read().split("results = []")[0])
exec(open('fireside_shift_parse_test.py').read().split("if __name__")[0])

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

def collapse_repeats(s):
    return re.sub(r'(.)\1{2,}', r'\1', s)

NEG_ANCHORS = ['no','none','nope','na','n/a','nah','nada','nothing','not']
def is_fuzzy_negative(token):
    t = collapse_repeats(token.lower().strip('!.:) '))
    if not t or len(t) > 6: return False
    return any(levenshtein(t, anchor) <= 1 for anchor in NEG_ANCHORS)

def is_negative_phrase(text):
    t = text.strip()
    if len(t) > 60: return False
    m = re.match(r"^([A-Za-z']+)\b", t)
    if not m: return False
    first = collapse_repeats(m.group(1).lower())
    return any(levenshtein(first, a) <= 1 for a in NEG_ANCHORS)

def norm_staffing(val):
    v = val.lower()
    if 'under' in v: return 'Understaffed'
    if 'over' in v: return 'Overstaffed'
    if 'just right' in v or 'perfect' in v or 'good staffing' in v: return 'Just Right'
    return 'Unclassified'

def norm_safety(val):
    v = val.strip()
    if v == '': return ('Blank', None)
    if is_fuzzy_negative(v) or is_negative_phrase(v): return ('No', None)
    vl = re.sub(r'[^a-z ]', '', v.lower()).strip()
    if vl in ('good','fine','great','ok','okay','all good','were good','we good','all good here','great!','fine!'):
        return ('No', None)
    return ('Flagged', v)

def is_meaningful_tardy(text):
    t = text.strip()
    if is_fuzzy_negative(t) or is_negative_phrase(t): return False
    tl = t.lower().strip('!.:) ')
    return tl != '' and not tl.startswith('no ')

DAY_WORDS_G = re.compile(r'\b(mon|tue|wed|thu|fri|sat|sun)\w*\b', re.I)
SHIFT_WORD_G = re.compile(r'\b(open(ing)?|morn\w*|mid|close|closing|night)\b', re.I)

def parse_name_fireside(text):
    first_part = re.split(r'[,/]', text)[0]
    cut_points = [m.start() for m in re.finditer(r'[/\-\d]', first_part)]
    dm = DAY_WORDS_G.search(first_part)
    if dm: cut_points.append(dm.start())
    sm = SHIFT_WORD_G.search(first_part)
    if sm: cut_points.append(sm.start())
    cut = min(cut_points) if cut_points else len(first_part)
    name = first_part[:cut].strip(' -/')
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

FIELD_MAP = [
    (2, 'Staffing'),
    (3, 'Line times / leaderboard'),
    (4, 'Best team player / wear more hats'),
    (5, 'Tardy / early out'),
    (6, 'Xbro / non-negotiables'),
    (7, 'Safety hazards'),
    (8, 'Additional comments'),
    (9, 'Fridge seals cleaned'),
    (10, 'Closing: Verifone WiFi'),
    (11, 'Closing: food inventory texted to managers'),
    (12, 'Closing: safe/tills/iPads/doors checklist'),
]

TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
DAYS = 60
TODAY_INDEX = DAYS - 1

def day_index_for(dt):
    return TODAY_INDEX - (TODAY.date() - dt.date()).days

def safe_get(row, idx):
    return row[idx] if idx < len(row) else ''

def build_fireside(csv_path, shift_cutoff):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    data = rows[1:]

    out = []
    for r in data:
        ts = r[0].strip()
        if not ts: continue
        dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        di = day_index_for(dt)
        if not (0 <= di <= TODAY_INDEX): continue
        namefield = safe_get(r, 1)
        if not namefield.strip(): continue
        shift, method = parse_shift(namefield, dt)
        name = parse_name_fireside(namefield)

        staffing_raw = safe_get(r, 2)
        team_player = safe_get(r, 4)
        tardy_raw = safe_get(r, 5)
        xbro_raw = safe_get(r, 6)
        safety_raw = safe_get(r, 7)
        comments = safe_get(r, 8)

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)

        cutoff_h, cutoff_m = shift_cutoff[shift]
        if shift == 'Close':
            if dt.hour == cutoff_h: is_late = dt.minute > cutoff_m
            elif dt.hour > cutoff_h and dt.hour < 24: is_late = True
            else: is_late = False
        else:
            is_late = (dt.hour, dt.minute) > (cutoff_h, cutoff_m)

        flags = []
        if staffing == 'Understaffed':
            flags.append({'kind':'bad','employee':None,'text':'Shift reported understaffed.'})
        if team_player.strip() and team_player.strip().lower() not in ('n/a','na','no'):
            flags.append({'kind':'good','employee':None,'text':team_player.strip()})
        if is_meaningful_tardy(tardy_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Tardy/early-out note: {tardy_raw.strip()}'})
        if safety_status == 'Flagged':
            flags.append({'kind':'bad','employee':None,'text':f'Hazard reported: {safety_detail}'})
        if xbro_raw.strip() and re.search(r'struggl|coach|didn|did not|couldn', xbro_raw, re.I):
            flags.append({'kind':'bad','employee':None,'text':xbro_raw.strip()})
        if comments.strip():
            is_bad = bool(re.search(r'rough|slam|short staff|struggl|behind|disorganiz|heated|upset', comments, re.I))
            flags.append({'kind':'bad' if is_bad else 'good','employee':None,'text':comments.strip()})
        if is_late:
            flags.append({'kind':'bad','employee':None,'text':f'Recap submitted late — arrived {dt.strftime("%-I:%M %p")}, after the {cutoff_h:02d}:{cutoff_m:02d} grace-period cutoff for {shift}.'})

        full_recap = {}
        for idx, label in FIELD_MAP:
            full_recap[label] = safe_get(r, idx)

        mentions = []
        for nm in extract_leading_names(team_player): mentions.append((nm, 'good', team_player))
        for nm in extract_possessive(comments): mentions.append((nm, 'good', comments))
        for nm in extract_shoutout(comments): mentions.append((nm, 'good', comments))
        for nm in extract_tardy_names(tardy_raw): mentions.append((nm, 'bad', tardy_raw))
        for nm in extract_xbro_coach_names(xbro_raw): mentions.append((nm, 'bad', xbro_raw))

        seen, named_mentions = set(), []
        for nm, sentiment, src in mentions:
            canon = title_name(nm)
            key = (canon.lower(), sentiment)
            if key in seen: continue
            seen.add(key)
            named_mentions.append({'name': canon, 'kind': sentiment, 'source': src.strip()[:160]})

        out.append({
            'shop': 'Fireside', 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comments.strip() if comments.strip() else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    records = build_fireside('fireside_recap_raw.csv', {'Open': (11,15), 'Mid': (18,15), 'Close': (23,15)})
    with open('fireside_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} Fireside records built')
    late_count = sum(1 for r in records if r['isLate'])
    print(f'{late_count} of {len(records)} submitted late')
    total_mentions = sum(len(r['namedMentions']) for r in records)
    print(f'{total_mentions} total named mentions')
    flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
    print(f'{flagged_hazards} recaps with a real flagged hazard')
