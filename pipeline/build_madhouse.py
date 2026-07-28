import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
exec(open('extract_names.py').read().split("results = []")[0])  # reuse name-extraction functions

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
    return re.sub(r'(.)\1{2,}', r'\1', s)  # "nahhh" -> "nah", "noooo" -> "no"

NEG_ANCHORS = ['no','none','nope','na','n/a','nah','nada','nothing']
def is_fuzzy_negative(token):
    t = collapse_repeats(token.lower().strip('!.:) '))
    if not t or len(t) > 6: return False
    return any(levenshtein(t, anchor) <= 1 for anchor in NEG_ANCHORS)

NEG_PHRASE_START = re.compile(r'^(no|none|nada|nothing|nope|nah)\b', re.I)
def is_negative_phrase(text):
    t = text.strip()
    return bool(NEG_PHRASE_START.match(collapse_repeats(t))) and len(t) <= 55

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

# ---- Madhouse-specific shift parser ----
KW_OPEN = re.compile(r'\b(open(ing)?|morning|morn)\b', re.I)
KW_MID = re.compile(r'\bmid(dy)?\b', re.I)
KW_CLOSE = re.compile(r'\b(close|closing|night)\b', re.I)
SUBSTR_MID = re.compile(r'mid', re.I)
SUBSTR_CLOSE = re.compile(r'clos', re.I)
SUBSTR_OPEN = re.compile(r'open|morn', re.I)

def parse_shift_madhouse(text, submission_dt):
    if KW_OPEN.search(text): return 'Open', 'keyword'
    if KW_MID.search(text): return 'Mid', 'keyword'
    if KW_CLOSE.search(text): return 'Close', 'keyword'
    if SUBSTR_CLOSE.search(text): return 'Close', 'substr-typo'
    if SUBSTR_MID.search(text): return 'Mid', 'substr-typo'
    if SUBSTR_OPEN.search(text): return 'Open', 'substr-typo'
    hr = submission_dt.hour
    if 4 <= hr <= 13: return 'Open', 'submission-hour-fallback'
    if 14 <= hr <= 19: return 'Mid', 'submission-hour-fallback'
    return 'Close', 'submission-hour-fallback'

DAY_WORDS_G = re.compile(r'\b(mon|tue|wed|thu|fri|sat|sun)\w*\b', re.I)
SHIFT_WORD_G = re.compile(r'\b(open(ing)?|morn(ing)?|mid(dy)?|close|closing|night)\b', re.I)

def parse_name_madhouse(text):
    # names here are typically comma-separated: "Sophia Drumright, 5-12, 7/20"
    first_part = text.split(',')[0]
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
    (6, 'Morning SL: gravers feedback'),
    (7, 'Safety hazards'),
    (8, 'Additional comments'),
    (9, 'Xbro non-negotiables struggle'),
    (10, 'Shift chore completed'),
    (11, 'Closing: Verifone WiFi'),
    (12, 'Closing: bakery item inventory'),
]

TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
DAYS = 60
TODAY_INDEX = DAYS - 1

def day_index_for(dt):
    return TODAY_INDEX - (TODAY.date() - dt.date()).days

def safe_get(row, idx):
    return row[idx] if idx < len(row) else ''

def build_madhouse(csv_path, shift_cutoff):
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
        if not namefield.strip(): continue  # skip old legacy rows with no name/shift info at all
        shift, method = parse_shift_madhouse(namefield, dt)
        name = parse_name_madhouse(namefield)

        staffing_raw = safe_get(r, 2)
        line_times = safe_get(r, 3)
        team_player = safe_get(r, 4)
        tardy_raw = safe_get(r, 5)
        gravers_feedback = safe_get(r, 6)
        safety_raw = safe_get(r, 7)
        comments = safe_get(r, 8)
        xbro_raw = safe_get(r, 9)
        chore_raw = safe_get(r, 10)
        closing_verifone = safe_get(r, 11)
        closing_bakery = safe_get(r, 12)

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)

        cutoff_h, cutoff_m = shift_cutoff[shift]
        is_late = (dt.hour, dt.minute) > (cutoff_h, cutoff_m) if shift != 'Close' else \
                  not (dt.hour < cutoff_h or (dt.hour == cutoff_h and dt.minute <= cutoff_m)) and dt.hour >= 4
        # Close cutoff crosses midnight (12:15am) -- treat hours 4-23 as "still same day, before midnight" (always late-eligible check only applies post-midnight window)
        if shift == 'Close':
            # late if submitted after 00:15 but still "night" (i.e., hour in 0..3 after cutoff) -- hour 0, minute>15 is late; hours 1-3 always late; hours >=4 shouldn't happen for a close but guard anyway
            if dt.hour == 0:
                is_late = dt.minute > cutoff_m
            elif 1 <= dt.hour <= 3:
                is_late = True
            else:
                is_late = False

        flags = []
        if staffing == 'Understaffed':
            flags.append({'kind':'bad','employee':None,'text':'Shift reported understaffed.'})
        if is_meaningful_generic(team_player):
            flags.append({'kind':'good','employee':None,'text':team_player.strip()})
        if is_meaningful_tardy(tardy_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Tardy/early-out note: {tardy_raw.strip()}'})
        if safety_status == 'Flagged':
            flags.append({'kind':'bad','employee':None,'text':f'Hazard reported: {safety_detail}'})
        if xbro_raw.strip() and is_meaningful_generic(xbro_raw):
            flags.append({'kind':'bad','employee':None,'text':f'Xbro coaching: {xbro_raw.strip()}'})
        if is_meaningful_generic(chore_raw) and not re.match(r'^(yes|yep|yeah|yup)\b', chore_raw.strip(), re.I):
            flags.append({'kind':'bad','employee':None,'text':f'Shift chore not completed: {chore_raw.strip()}'})
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
            'shop': 'Mad', 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comments.strip() if comments.strip() else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    records = build_madhouse('madhouse_recap_raw.csv', {'Open': (12,15), 'Mid': (17,15), 'Close': (0,15)})
    with open('madhouse_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} Madhouse records built')
    late_count = sum(1 for r in records if r['isLate'])
    print(f'{late_count} of {len(records)} submitted late')
    total_mentions = sum(len(r['namedMentions']) for r in records)
    print(f'{total_mentions} total named mentions')
    flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
    print(f'{flagged_hazards} recaps with a real flagged hazard')
