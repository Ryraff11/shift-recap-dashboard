import json, re

STOP_LEAD_WORDS = {'honestly','overall','unfortunately','no','none','nobody','everyone','everybody',
                    'we','i','it','na','n/a','nope','yes','xbro','x','both','really','literally',
                    'seriously','totally','definitely','genuinely','basically','especially','truly','actually'}
NEGATIVE_ONLY = {'no','none','nobody','n/a','na','nope','no one','no tardies','nan'}

TRIGGER = re.compile(
    r'\b(was|were|did|is|has|hopped|ran|went|killed|crushed|blew|shinned|shined|definitely|absolutely|really|slayed|nailed|rocked)\b',
    re.I
)

STOPWORDS = {'i','we','he','she','they','one','someone','anyone','everyone','nobody','somebody',
             'but','and','on','to','for','with','the','a','an','as','that','this','all','no','none',
             'na','nan','it','is','was','her','him','them','us','you','ni','late','tardy','clock',
             'clocked','early','home','today'}

TRAILING_FILLER = {'honestly','really','seriously','literally','totally','definitely','genuinely',
                    'obviously','clearly','basically','especially','truly','actually','tho','though'}

def valid_name(tok):
    words = tok.lower().split()
    if not words:
        return False
    if any(w in STOPWORDS for w in words):
        return False
    if len(words) > 3:
        return False
    return True

def clean_token(tok):
    return tok.strip(' .,!?\u2018\u2019\'"')

def split_names(segment):
    parts = re.split(r'\s*(?:,|&|\+|\band\b)\s*', segment, flags=re.I)
    out = []
    for p in parts:
        p = clean_token(p)
        if not p:
            continue
        words = p.split()
        while words and words[-1].lower() in TRAILING_FILLER:
            words.pop()
        p = ' '.join(words)
        if p and valid_name(p):
            out.append(p)
    return out

TEAM_PLAYER_PHRASE = re.compile(r'(?:best\s+)?team\s+player\s+(?:was|is)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)', re.I)

def extract_leading_names(text):
    if not text:
        return []
    m = TEAM_PLAYER_PHRASE.search(text)
    if m:
        tok = clean_token(m.group(1))
        return split_names(tok) if valid_name(tok) else []
    m = TRIGGER.search(text)
    if not m:
        return []
    segment = text[:m.start()].strip()
    words = segment.split()
    while words and words[0].lower() in STOP_LEAD_WORDS:
        words.pop(0)
    segment = ' '.join(words)
    return split_names(segment)

def extract_possessive(text):
    names = []
    for m in re.finditer(r"([A-Z][a-zA-Z]+)[\u2018\u2019']s\b", text):
        if valid_name(m.group(1)):
            names.append(m.group(1))
    return names

def extract_shoutout(text):
    names = []
    for m in re.finditer(r'shout\s*out\s+([A-Za-z]+)', text, re.I):
        tok = clean_token(m.group(1))
        if valid_name(tok):
            names.append(tok)
    return names

def _levenshtein_local(a, b):
    if a == b: return 0
    if len(a) < len(b): a, b = b, a
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0]*len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+(ca!=cb))
        prev = cur
    return prev[-1]

def _starts_with_negative(text):
    m = re.match(r"^([A-Za-z']+)", text.strip())
    if not m: return False
    first = re.sub(r'(.)\1{2,}', r'\1', m.group(1).lower())
    anchors = ['no','none','nope','na','nah','nada','nothing','not']
    return any(_levenshtein_local(first, a) <= 1 for a in anchors)

def extract_tardy_names(text):
    """Names associated with tardy/early-out mentions -- always scan for specific
    patterns first, since a sentence can open negatively ('No one was late...')
    but still contain a real mention later ('...but I sent Katelyn home early')."""
    t = text.strip()
    tl = t.lower().strip('!.:) ')
    names = []

    for m in re.finditer(r'sent\s+([A-Za-z]+)\s+home', t, re.I):
        tok = clean_token(m.group(1))
        if valid_name(tok):
            names.append(tok)

    for m in re.finditer(r'\b([A-Za-z]+)\s+(?:was late|clocked in|late clocking)', t, re.I):
        tok = clean_token(m.group(1))
        if valid_name(tok):
            names.append(tok)

    for m in re.finditer(r'([A-Za-z]+(?:\s*,\s*[A-Za-z]+)*(?:\s*(?:,?\s*and|&)\s*[A-Za-z]+)?)\s+(?:all\s+)?went home early', t, re.I):
        names.extend(split_names(m.group(1)))

    if names:
        return names

    # fallback: whole field IS just a name (e.g. tardy field == "Lily G")
    if not _starts_with_negative(t) and tl not in ('', 'na', 'n/a') \
       and len(t.split()) <= 3 and t[0:1].isupper() \
       and not re.search(r'\b(no|none|late|tardy|clock|home|early)\b', t, re.I):
        names.append(t)

    return names


def extract_xbro_coach_names(text):
    names = []
    on_matches = list(re.finditer(r'\bcoach(?:ed|ing)?\s+([A-Za-z]+(?:\s*(?:&|and)\s*[A-Za-z]+)?)\s+on\b', text, re.I))
    if on_matches:
        for m in on_matches:
            names.extend(split_names(m.group(1)))
    else:
        for m in re.finditer(r'\bcoach(?:ed|ing)?\s+([A-Za-z]+(?:\s*(?:&|and)\s*[A-Za-z]+)?)(?!\w)', text, re.I):
            seg = m.group(1)
            if seg.lower() not in ('but','it','them'):
                names.extend(split_names(seg))
    return names

results = []
for r in recs:
    fr = r['fullRecap']
    mentions = []  # list of (name, sentiment, source_text)

    for name in extract_leading_names(fr['teamPlayer']):
        mentions.append((name, 'good', fr['teamPlayer']))

    for name in extract_possessive(fr['comments']):
        mentions.append((name, 'good', fr['comments']))
    for name in extract_shoutout(fr['comments']):
        mentions.append((name, 'good', fr['comments']))

    for name in extract_tardy_names(fr['tardy']):
        mentions.append((name, 'bad', fr['tardy']))

    for name in extract_xbro_coach_names(fr['xbro']):
        mentions.append((name, 'bad', fr['xbro']))

    seen = set()
    deduped = []
    for name, sentiment, src in mentions:
        key = (name.lower(), sentiment)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((name, sentiment, src))
    mentions = deduped

    results.append({'dayIndex': r['dayIndex'], 'shift': r['shift'], 'author': r['employee'], 'mentions': mentions})

for r in results:
    print(f"day {r['dayIndex']} {r['shift']} (by {r['author']}):")
    for name, sentiment, src in r['mentions']:
        print(f"   [{sentiment}] {name!r}  <- {src[:70]!r}")
    print()
