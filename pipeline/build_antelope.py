import csv, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
from shift_cutoffs import cutoff_for
exec(open('extract_names.py').read().split("results = []")[0])

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

def norm_food(val):
    v = val.strip()
    if v == '': return 'Blank'
    vl = v.lower()
    if 'yes' in vl: return 'Yes'
    if 'nope' in vl or vl.startswith('no'): return 'No / In progress'
    return 'Other: ' + v

def is_meaningful_tardy(text):
    t = text.strip()
    if is_fuzzy_negative(t) or is_negative_phrase(t): return False
    tl = t.lower().strip('!.:) ')
    return tl != '' and not tl.startswith('no ')

SHIFT_PATTERNS = [
    (re.compile(r'\b(open(ing)?|morning)\b', re.I), 'Open'),
    (re.compile(r'\bmid\b', re.I), 'Mid'),
    (re.compile(r'\b(close|closing|night)\b', re.I), 'Close'),
]
DAY_WORDS_LOCAL = re.compile(r'\b(mon|tue|wed|thu|fri|sat|sun)\w*\b', re.I)
SHIFT_WORD_LOCAL = re.compile(r'\b(open(ing)?|morning|mid|close|closing|night)\b', re.I)

def parse_shift(text):
    for pat, label in SHIFT_PATTERNS:
        if pat.search(text): return label
    return 'Unknown'

def parse_name_full(text):
    cut_points = [m.start() for m in re.finditer(r'[/\-\d]', text)]
    dm = DAY_WORDS_LOCAL.search(text)
    if dm: cut_points.append(dm.start())
    sm = SHIFT_WORD_LOCAL.search(text)
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

TODAY = datetime.now(ZoneInfo('America/Los_Angeles'))
DAYS = 60
TODAY_INDEX = DAYS - 1
SHIFT_CUTOFF = {'Open': (11,15), 'Mid': (18,15), 'Close': (23,45)}

def day_index_for(dt):
    return TODAY_INDEX - (TODAY.date() - dt.date()).days

def safe_get(row, idx):
    return row[idx] if idx < len(row) else ''

def build_antelope(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    data = rows[1:]

    out = []
    for r in data:
        ts = safe_get(r, 0).strip()
        if not ts: continue
        try:
            dt = datetime.strptime(ts, '%m/%d/%Y %H:%M:%S')
        except ValueError:
            continue
        di = day_index_for(dt)
        if not (0 <= di <= TODAY_INDEX): continue
        namefield = safe_get(r, 1)
        shift = parse_shift(namefield)
        if shift not in ('Open', 'Mid', 'Close'): continue
        name = parse_name_full(namefield)

        staffing_raw = safe_get(r, 2)
        line_times = safe_get(r, 3)
        team_player = safe_get(r, 4)
        tardy_raw = safe_get(r, 5)
        food_inv_raw = safe_get(r, 6)
        safety_raw = safe_get(r, 7)
        xbro = safe_get(r, 8)
        comments = safe_get(r, 9)
        closing_verifone = safe_get(r, 10)
        closing_checklist = safe_get(r, 11)

        staffing = norm_staffing(staffing_raw)
        safety_status, safety_detail = norm_safety(safety_raw)
        food_inventory = norm_food(food_inv_raw)

        cutoff_h, cutoff_m = cutoff_for('Antelope', shift, dt)
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
        if xbro.strip() and re.search(r'struggl|coach|didn|did not|couldn', xbro, re.I):
            flags.append({'kind':'bad','employee':None,'text':xbro.strip()})
        if comments.strip():
            is_bad = bool(re.search(r'rough|slam|short staff|struggl|behind|disorganiz|heated|upset', comments, re.I))
            flags.append({'kind':'bad' if is_bad else 'good','employee':None,'text':comments.strip()})
        if is_late:
            flags.append({'kind':'bad','employee':None,'text':f'Recap submitted late — arrived {dt.strftime("%-I:%M %p")}, after the {cutoff_h:02d}:{cutoff_m:02d} grace-period cutoff for {shift}.'})

        full_recap = {
            'Staffing': staffing_raw,
            'Line times / leaderboard': line_times,
            'Team player / needed to step up': team_player,
            'Tardy / early out': tardy_raw,
            'Food inventory sheet': food_inventory,
            'Safety hazards': safety_raw,
            'Xbro / non-negotiables': xbro,
            'Additional comments': comments,
            'Closing: Verifone WiFi': closing_verifone,
            'Closing checklist': closing_checklist,
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
            'shop': 'Antelope', 'shift': shift, 'dayIndex': di, 'timestamp': ts,
            'employee': name, 'isLate': is_late,
            'bestPlayer': None, 'needsHats': None, 'tardy': None, 'hazard': None, 'xbroStruggle': None,
            'comment': comments.strip() if comments.strip() else 'No comments, standard shift.',
            'flags': flags, 'fullRecap': full_recap, 'namedMentions': named_mentions,
        })
    return out

if __name__ == '__main__':
    records = build_antelope('antelope_recap_raw.csv')
    with open('antelope_records_full_window.json', 'w') as f:
        json.dump(records, f, indent=2)
    print(f'{len(records)} Antelope records built')
    late_count = sum(1 for r in records if r['isLate'])
    print(f'{late_count} of {len(records)} submitted late')
    total_mentions = sum(len(r['namedMentions']) for r in records)
    print(f'{total_mentions} total named mentions')
    flagged_hazards = sum(1 for r in records if any(f['text'].startswith('Hazard reported') for f in r['flags']))
    print(f'{flagged_hazards} recaps with a real flagged hazard')
