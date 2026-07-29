import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
from shift_cutoffs import cutoff_for
exec(open('extract_names.py').read().split("results = []")[0])
exec(open('lichen_shift_parse_test.py').read().split("if __name__")[0])

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
    if 'perfect' in v or 'well staffed' in v or 'good staffing' in v: return 'Just Right'
    return 'Unclassified'

def norm_safety(val):
    v = val.strip()
    if v == '': return ('Blank', None)
    if is_fuzzy_negative(v) or is_negative_phrase(v): return ('No', None)
    return ('Flagged', v)

def is_meaningful_tardy(text):
    t = text.strip()
    if is_fuzzy_negative(t) or is_negative_phrase(t): return False
    tl = t.lower().strip('!.:) ')
    return tl != '' and not tl.startswith('no ')

def is_meaningful_generic(text):
    t = text.strip()
    if not t: return False
    if is_fuzzy_negative(t) or is_negative_phrase(t): return False
    return True

DAY_WORDS_G = re.compile(r'\b(mon|tue|wed|thu|fri|sat|sun)\w*\b', re.I)
SHIFT_WORD_G = re.compile(r'\b(open(ing)?|morn\w*|mid|close|closing|night)\b', re.I)

def parse_name_lichen(text):
    first_part = text.split('/')[0]
    cut_points = [m.start() for m in re.finditer(r'[/\-\d]', first_part)]
    dm = DAY_WORDS_G.search(first_part)
    if dm: cut_points.append(dm.start())
    sm = SHIFT_WORD_G.search(first_part)
    if sm: cut_points.append(sm.start())
    cut = min(cut_points) if cut_points else len(first_part)
    name = first_part[:cut].strip(' -/\n')
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
    (5, 'Staffing'),
    (7, 'Line times / leaderboard'),
    (24, 'Times throughout shift'),
    (6, 'Best team player / wear more hats'),
    (3, 'Tardy / early out'),
    (8, 'Coaching notes'),
    (9, 'What could have gone smoother'),
    (10, 'Safety hazards'),
    (12, 'Additional comments'),
    (13, 'Fridge seals cleaned'),
    (14, 'New staffing/XBRO: went well / challenging'),
    (15, 'XBRO effectiveness'),
    (16, 'Bought into new system'),
    (17, 'Struggled with new staffing/XBRO'),
    (18, 'Clamps'),
    (19, 'Closing checklist'),
    (20, 'Quarterly contest tallies'),
    (21, 'Xbro non-negotiables struggle'),
    (22, 'Chef position feedback'),
    (11, 'Closing: Verifone WiFi'),
    (25, 'Aug contest: OA runner'),
    (26, 'Aug contest: why'),
]

TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
DAYS = 60
TODAY_INDEX = DAYS - 1

def day_index_for(dt):
    return TODAY_INDEX - (TODAY.date() - dt.date()).days

def safe_get(row, idx):
    return row[idx] if idx < len(row) else ''

def build_lichen(csv_path, shift_cutoff):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    data = rows[1:]

    out = []
    for r in data:
        ts = r[0].strip()
        if not ts: continue
        try:
            dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        except ValueError:
            continue
        di = day_index_for(dt)
        if not (0 <= di <= TODAY_INDEX): continue
        namefield = safe_get(r, 1)
        if not namefield.strip(): continue
        shift, method = parse_shift(namefield, dt)
        name = parse_name_lichen(namefield)

        staffing_raw = safe_get(r, 5)
        team_player = safe_get(r, 6)
        tardy_raw = safe_get(r, 3)
        coaching_raw = safe_get(r, 8)
        safety_raw = safe_get(r, 10)
        comments = safe_get(r, 12)
        bought_in = safe_get(r, 16)
        struggled = safe_get(r, 17)
        xbro_struggle_raw = safe_get(r, 21)
        aug_contest_name = safe_get(r, 25)

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)

        cutoff_h, cutoff_m = cutoff_for('Lichen', shift, dt)
        if shift == 'Close':
            if dt.hour == 0: is_late = dt.minute > cutoff_m
            elif 1 <= dt.hour <= 3: is_late = True
            else: is_late = False
        else:
            is_late = (dt.hour, dt.minute) > (cutoff_h, cutoff_m)

        flags = []
        if staffing == 'Understaffed':
            flags.append({'kind':'bad','employee':None,'text':'Shift reported understaffed.'})
        if is_meaningful_generic(team_player):
            flags.append({'kind':'good','employee':None,'text':team_player.strip()})
        if is_meaningful_generic(bought_in):
            flags.append({'kind':'good','employee':None,'text':f'Bought into new system: {bought_in.strip()}'})
        if is_meaningful_tardy(tardy_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Tardy/early-out note: {tardy_raw.strip()}'})
        if is_meaningful_generic(coaching_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Coached: {coaching_raw.strip()}'})
        if is_meaningful_generic(struggled):
            flags.append({'kind':'bad','employee':None,'text':f'Struggled with new staffing/XBRO: {struggled.strip()}'})
        if is_meaningful_generic(xbro_struggle_raw):
            flags.append({'kind':'bad','employee':None,'text':xbro_struggle_raw.strip()})
        if safety_status == 'Flagged':
            flags.append({'kind':'bad','employee':None,'text':f'Hazard reported: {safety_detail}'})
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
        for nm in extract_leading_names(bought_in): mentions.append((nm, 'good', bought_in))
        for nm in extract_possessive(comments): mentions.append((nm, 'good', comments))
        for nm in extract_shoutout(comments): mentions.append((nm, 'good', comments))
        if is_meaningful_generic(aug_contest_name) and len(aug_contest_name.split()) <= 3:
            mentions.append((aug_contest_name.strip(), 'good', aug_contest_name))
        for nm in extract_tardy_names(tardy_raw): mentions.append((nm, 'bad', tardy_raw))
        for nm in extract_xbro_coach_names(coaching_raw): mentions.append((nm, 'bad', coaching_raw))
        for nm in extract_leading_names(struggled): mentions.append((nm, 'bad', struggled))
        for nm in extract_xbro_coach_names(xbro_struggle_raw): mentions.append((nm, 'bad', xbro_struggle_raw))

        seen, named_mentions = set(), []
        for nm, sentiment, src in mentions:
            canon = title_name(nm)
            key = (canon.lower(), sentiment)
            if key in seen: continue
            seen.add(key)
            named_mentions.append({'name': canon, 'kind': sentiment, 'source': src.strip()[:160]})

        out.append({
            'shop': 'Lichen', 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comments.strip() if comments.strip() else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    records = build_lichen('lichen_recap_raw.csv', {'Open': (12,15), 'Mid': (19,15), 'Close': (0,15)})
    with open('lichen_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} Lichen records built')
    late_count = sum(1 for r in records if r['isLate'])
    print(f'{late_count} of {len(records)} submitted late')
    total_mentions = sum(len(r['namedMentions']) for r in records)
    print(f'{total_mentions} total named mentions')
    flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
    print(f'{flagged_hazards} recaps with a real flagged hazard')
