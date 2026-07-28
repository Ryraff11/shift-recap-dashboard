import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
exec(open('extract_names.py').read().split("results = []")[0])
exec(open('manz_shift_parse_test.py').read().split("if __name__")[0])

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
    if vl in ('good','fine','great','ok','okay','all good','were good','we good'):
        return ('No', None)
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

def parse_name_manz(text):
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
    (4, 'Best percentage / leaderboard hour'),
    (5, 'What could have gone smoother'),
    (6, 'Best team player / wear more hats'),
    (7, 'Tardy / early out'),
    (8, 'Tips split confirmed'),
    (10, 'Safety hazards'),
    (11, 'Fridge gaskets wiped'),
    (12, 'Xbro / non-negotiables'),
    (13, 'Additional comments'),
    (24, 'Bought into new system'),
    (25, 'Struggled with new staffing'),
    (26, 'Biggest clamp'),
    (27, 'XBRO feedback'),
    (28, 'Forgot single-drink-claim comp'),
    (30, 'Perfect pour comp'),
    (31, 'Remake comp'),
    (32, 'Caught fraud apps / bday drinks w/o ID'),
    (33, 'Got shift change'),
    (34, 'Best hourly window average'),
    (35, 'Cleanest person on shift'),
    (36, 'Window contest winner'),
    (37, 'Window contest: why'),
    (38, 'Cleanliness contest winner'),
    (39, 'Cleanliness contest: why'),
    (9, 'Closing: Verifone WiFi'),
]

TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
DAYS = 60
TODAY_INDEX = DAYS - 1

def day_index_for(dt):
    return TODAY_INDEX - (TODAY.date() - dt.date()).days

def safe_get(row, idx):
    return row[idx] if idx < len(row) else ''

def build_manz(csv_path):
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
        name = parse_name_manz(namefield)
        grp = day_group(dt.weekday())
        cutoff_h, cutoff_m = SHIFT_CUTOFFS_BY_GROUP[grp][shift]

        staffing_raw = safe_get(r, 2)
        team_player = safe_get(r, 6)
        tardy_raw = safe_get(r, 7)
        safety_raw = safe_get(r, 10)
        xbro_raw = safe_get(r, 12)
        comments = safe_get(r, 13)
        bought_in = safe_get(r, 24)
        struggled = safe_get(r, 25)
        forgot_claim = safe_get(r, 28)
        perfect_pour = safe_get(r, 30)
        cleanest = safe_get(r, 35)
        window_winner = safe_get(r, 36)
        cleanliness_winner = safe_get(r, 38)

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)

        if shift == 'Close':
            if dt.hour == cutoff_h: is_late = dt.minute > cutoff_m
            elif dt.hour > cutoff_h and dt.hour < 24: is_late = True
            elif 0 <= dt.hour <= 3: is_late = True
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
        if is_meaningful_generic(perfect_pour):
            flags.append({'kind':'good','employee':None,'text':f'Perfect pour comp: {perfect_pour.strip()}'})
        if is_meaningful_generic(cleanest):
            flags.append({'kind':'good','employee':None,'text':f'Cleanest on shift: {cleanest.strip()}'})
        if is_meaningful_generic(window_winner) and len(window_winner.split()) <= 3:
            flags.append({'kind':'good','employee':None,'text':f'Window contest: {window_winner.strip()}'})
        if is_meaningful_generic(cleanliness_winner) and len(cleanliness_winner.split()) <= 3:
            flags.append({'kind':'good','employee':None,'text':f'Cleanliness contest: {cleanliness_winner.strip()}'})
        if is_meaningful_tardy(tardy_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Tardy/early-out note: {tardy_raw.strip()}'})
        if is_meaningful_generic(struggled):
            flags.append({'kind':'bad','employee':None,'text':f'Struggled with new staffing: {struggled.strip()}'})
        if is_meaningful_generic(forgot_claim):
            flags.append({'kind':'bad','employee':None,'text':f'Forgot single-drink claim: {forgot_claim.strip()}'})
        if safety_status == 'Flagged':
            flags.append({'kind':'bad','employee':None,'text':f'Hazard reported: {safety_detail}'})
        if xbro_raw.strip() and re.search(r'struggl|coach|didn|did not|couldn', xbro_raw, re.I):
            flags.append({'kind':'bad','employee':None,'text':xbro_raw.strip()})
        if comments.strip():
            is_bad = bool(re.search(r'rough|slam|short staff|struggl|behind|disorganiz|heated|upset', comments, re.I))
            flags.append({'kind':'bad' if is_bad else 'good','employee':None,'text':comments.strip()})
        if is_late:
            flags.append({'kind':'bad','employee':None,'text':f'Recap submitted late — arrived {dt.strftime("%-I:%M %p")}, after the {cutoff_h:02d}:{cutoff_m:02d} grace-period cutoff for {shift} ({"Mon/Wed/Sat" if grp=="A" else "Tue/Thu/Fri/Sun"} schedule).'})

        full_recap = {}
        for idx, label in FIELD_MAP:
            full_recap[label] = safe_get(r, idx)

        mentions = []
        for nm in extract_leading_names(team_player): mentions.append((nm, 'good', team_player))
        for nm in extract_leading_names(bought_in): mentions.append((nm, 'good', bought_in))
        for nm in extract_possessive(comments): mentions.append((nm, 'good', comments))
        for nm in extract_shoutout(comments): mentions.append((nm, 'good', comments))
        if is_meaningful_generic(perfect_pour) and len(perfect_pour.split()) <= 3:
            mentions.append((perfect_pour.strip(), 'good', perfect_pour))
        if is_meaningful_generic(cleanest) and len(cleanest.split()) <= 3:
            mentions.append((cleanest.strip(), 'good', cleanest))
        if is_meaningful_generic(window_winner) and len(window_winner.split()) <= 3:
            mentions.append((window_winner.strip(), 'good', window_winner))
        if is_meaningful_generic(cleanliness_winner) and len(cleanliness_winner.split()) <= 3:
            mentions.append((cleanliness_winner.strip(), 'good', cleanliness_winner))
        for nm in extract_tardy_names(tardy_raw): mentions.append((nm, 'bad', tardy_raw))
        for nm in extract_xbro_coach_names(xbro_raw): mentions.append((nm, 'bad', xbro_raw))
        if is_meaningful_generic(forgot_claim) and len(forgot_claim.split()) <= 3:
            mentions.append((forgot_claim.strip(), 'bad', forgot_claim))

        seen, named_mentions = set(), []
        for nm, sentiment, src in mentions:
            canon = title_name(nm)
            key = (canon.lower(), sentiment)
            if key in seen: continue
            seen.add(key)
            named_mentions.append({'name': canon, 'kind': sentiment, 'source': src.strip()[:160]})

        out.append({
            'shop': 'Manz', 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comments.strip() if comments.strip() else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    records = build_manz('manz_recap_raw.csv')
    with open('manz_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} Manz records built')
    late_count = sum(1 for r in records if r['isLate'])
    print(f'{late_count} of {len(records)} submitted late')
    total_mentions = sum(len(r['namedMentions']) for r in records)
    print(f'{total_mentions} total named mentions')
    flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
    print(f'{flagged_hazards} recaps with a real flagged hazard')
