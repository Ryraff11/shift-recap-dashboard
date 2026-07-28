import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
exec(open('extract_names.py').read().split("results = []")[0])  # reuse name-extraction functions
exec(open('auburn_shift_parse_test.py').read().split("if __name__")[0])  # reuse parse_shift

DAY_WORDS_G = re.compile(r'\b(mon|tue|wed|thu|fri|sat|sun)\w*\b', re.I)
SHIFT_WORD_G = re.compile(r'\b(open(ing)?|morning|mid|close|closing|night|am|pm)\b', re.I)

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

NEG_ANCHORS = ['no','none','nope','na','n/a','nah','nada','nothing']
def is_fuzzy_negative(token):
    t = token.lower().strip('!.:) ')
    if not t or len(t) > 6: return False
    return any(levenshtein(t, anchor) <= 1 for anchor in NEG_ANCHORS)

NEG_PHRASE_START = re.compile(r'^(no|none|nada|nothing|nope)\b', re.I)
def is_negative_phrase(text):
    t = text.strip()
    return bool(NEG_PHRASE_START.match(t)) and len(t) <= 55

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
    if vl in ('no','none','nope','na','nah',''): return ('No', None)
    return ('Flagged', v)

def is_meaningful_tardy(text):
    t = text.strip()
    if is_fuzzy_negative(t): return False
    tl = t.lower().strip('!.:) ')
    return tl != '' and tl not in {'no','none','nope','na','n/a','nothing'} and not tl.startswith('no ')

def is_meaningful_generic(text):
    t = text.strip()
    if not t: return False
    if is_fuzzy_negative(t): return False
    tl = t.lower().strip('!.:) ')
    return tl not in {'no','none','nope','na','n/a','nothing','nobody'} and not tl.startswith('no ') and not tl.startswith('nobody')

# canonical (index, label) map -- order defines display order in the modal
FIELD_MAP = [
    (2, 'Shift time'),
    (3, 'Staffing'),
    (4, 'Rush timing'),
    (5, 'Cleanest on bar'),
    (6, 'Line times / leaderboard'),
    (7, 'Safety hazards'),
    (8, 'Xbro / non-negotiables'),
    (9, 'Coaching notes'),
    (10, 'Xbro effectiveness (1-5)'),
    (11, 'Team player (system buy-in)'),
    (12, 'Needs replacing / broken'),
    (13, 'Quarterly comp tallies (OAs not ready)'),
    (14, 'Closing: Verifone WiFi'),
    (15, 'Tardy / early-out'),
    (16, 'Fridge seals check'),
    (17, 'XBRO staffing struggles'),
    (18, 'Clamps'),
    (19, 'Closing: positionless helper'),
    (20, 'Closing: efficiency reflection'),
    (21, 'Expired milk check'),
    (22, 'Additional comments'),
    (23, 'Best team player / wear more hats'),
    (24, 'Culture competition'),
]

TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
DAYS = 60
TODAY_INDEX = DAYS - 1
SHIFT_CUTOFF = None  # set below once we have Auburn's cutoff times

def day_index_for(dt):
    return TODAY_INDEX - (TODAY.date() - dt.date()).days

def safe_get(row, idx):
    return row[idx] if idx < len(row) else ''

def build_auburn(csv_path, shift_cutoff):
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
        shift, method = parse_shift(r[1], dt)
        name = parse_name_full(r[1])

        staffing_raw = safe_get(r, 3)
        safety_raw = safe_get(r, 7)
        xbro_raw = safe_get(r, 8)
        coaching_raw = safe_get(r, 9)
        team_player_a = safe_get(r, 11)
        tardy_raw = safe_get(r, 15)
        xbro_staffing_struggle = safe_get(r, 17)
        closing_positionless = safe_get(r, 19)
        comments = safe_get(r, 22)
        team_player_b = safe_get(r, 23)
        culture_comp = safe_get(r, 24)
        cleanest = safe_get(r, 5)

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)

        cutoff_h, cutoff_m = shift_cutoff[shift]
        is_late = (dt.hour, dt.minute) > (cutoff_h, cutoff_m)

        flags = []
        if staffing == 'Understaffed':
            flags.append({'kind':'bad','employee':None,'text':'Shift reported understaffed.'})
        if team_player_b.strip() and team_player_b.strip().lower() not in ('n/a','na','no'):
            flags.append({'kind':'good','employee':None,'text':team_player_b.strip()})
        if team_player_a.strip() and team_player_a.strip().lower() not in ('n/a','na','no'):
            flags.append({'kind':'good','employee':None,'text':team_player_a.strip()})
        if is_meaningful_generic(cleanest):
            flags.append({'kind':'good','employee':None,'text':f'Cleanest on shift: {cleanest.strip()}'})
        if is_meaningful_generic(culture_comp):
            flags.append({'kind':'good','employee':None,'text':f'Culture competition: {culture_comp.strip()}'})
        if is_meaningful_generic(closing_positionless):
            flags.append({'kind':'good','employee':None,'text':f'Closing positionless helper: {closing_positionless.strip()}'})
        if is_meaningful_tardy(tardy_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Tardy/early-out note: {tardy_raw.strip()}'})
        if safety_status == 'Flagged':
            flags.append({'kind':'bad','employee':None,'text':f'Hazard reported: {safety_detail}'})
        if xbro_raw.strip() and re.search(r'struggl|coach|didn|did not|couldn', xbro_raw, re.I):
            flags.append({'kind':'bad','employee':None,'text':xbro_raw.strip()})
        if is_meaningful_generic(xbro_staffing_struggle):
            flags.append({'kind':'bad','employee':None,'text':f'XBRO staffing struggle: {xbro_staffing_struggle.strip()}'})
        if is_meaningful_generic(coaching_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Coached: {coaching_raw.strip()}'})
        if comments.strip():
            is_bad = bool(re.search(r'rough|slam|short staff|struggl|behind|disorganiz|heated|upset', comments, re.I))
            flags.append({'kind':'bad' if is_bad else 'good','employee':None,'text':comments.strip()})
        if is_late:
            flags.append({'kind':'bad','employee':None,'text':f'Recap submitted late — arrived {dt.strftime("%-I:%M %p")}, after the {cutoff_h:02d}:{cutoff_m:02d} grace-period cutoff for {shift}.'})

        full_recap = {}
        for idx, label in FIELD_MAP:
            full_recap[label] = safe_get(r, idx)

        mentions = []
        for nm in extract_leading_names(team_player_b): mentions.append((nm, 'good', team_player_b))
        for nm in extract_leading_names(team_player_a): mentions.append((nm, 'good', team_player_a))
        for nm in extract_leading_names(cleanest): mentions.append((nm, 'good', cleanest))
        for nm in extract_leading_names(culture_comp): mentions.append((nm, 'good', culture_comp))
        for nm in extract_leading_names(closing_positionless): mentions.append((nm, 'good', closing_positionless))
        for nm in extract_possessive(comments): mentions.append((nm, 'good', comments))
        for nm in extract_shoutout(comments): mentions.append((nm, 'good', comments))
        for nm in extract_tardy_names(tardy_raw): mentions.append((nm, 'bad', tardy_raw))
        for nm in extract_xbro_coach_names(xbro_raw): mentions.append((nm, 'bad', xbro_raw))
        for nm in extract_leading_names(xbro_staffing_struggle): mentions.append((nm, 'bad', xbro_staffing_struggle))
        for nm in extract_leading_names(coaching_raw): mentions.append((nm, 'bad', coaching_raw))

        seen, named_mentions = set(), []
        for nm, sentiment, src in mentions:
            canon = title_name(nm)
            key = (canon.lower(), sentiment)
            if key in seen: continue
            seen.add(key)
            named_mentions.append({'name': canon, 'kind': sentiment, 'source': src.strip()[:160]})

        out.append({
            'shop': 'Auburn', 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comments.strip() if comments.strip() else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    print("Run with cutoff times once provided.")

records = build_auburn('auburn_recap_raw.csv', {'Open': (12,15), 'Mid': (18,15), 'Close': (0,20)})
with open('auburn_records_full_window.json', 'w') as f:
    json.dump(records, f, indent=2)
print(f'{len(records)} Auburn records built')
late_count = sum(1 for r in records if r['isLate'])
print(f'{late_count} of {len(records)} submitted late')
total_mentions = sum(len(r['namedMentions']) for r in records)
print(f'{total_mentions} total named mentions')
flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
print(f'{flagged_hazards} recaps with a real flagged hazard')
