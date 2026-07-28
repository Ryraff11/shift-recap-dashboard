import json

COMMON_NICKNAMES = {
    'daph': 'daphne', 'ju': 'julia', 'jules': 'julia', 'julie': 'julia',
    'liz': 'elizabeth', 'beth': 'elizabeth', 'lizzie': 'elizabeth', 'eliza': 'elizabeth',
    'izzy': 'isabella', 'bella': 'isabella',
    'sam': 'samuel', 'sammy': 'samuel',
    'alex': 'alexander', 'lexi': 'alexandra',
    'cam': 'cameron',
    'abby': 'abigail',
    'maddie': 'madison', 'madi': 'madison', 'mads': 'madison',
    'katie': 'katherine', 'katy': 'katherine', 'kate': 'katherine',
    'ben': 'benjamin', 'benji': 'benjamin',
    'josh': 'joshua',
    'andy': 'andrew', 'drew': 'andrew',
    'zach': 'zachary', 'zack': 'zachary',
    'nate': 'nathan', 'nathaniel': 'nathan',
    'nick': 'nicholas', 'nico': 'nicholas',
    'mike': 'michael', 'mikey': 'michael',
    'chris': 'christopher',
    'matt': 'matthew',
    'dan': 'daniel', 'danny': 'daniel',
    'steve': 'steven',
    'tony': 'anthony',
    'will': 'william', 'bill': 'william', 'billy': 'william', 'liam': 'william',
    'tom': 'thomas', 'tommy': 'thomas',
    'rob': 'robert', 'bobby': 'robert', 'bob': 'robert',
    'jen': 'jennifer', 'jenny': 'jennifer',
    'pat': 'patricia',
    'gabe': 'gabriel',
    'tim': 'timothy', 'timmy': 'timothy',
    'ash': 'ashley',
    'em': 'emily', 'emmy': 'emily',
    'becca': 'rebecca', 'becky': 'rebecca',
    'gracie': 'grace',
    'cesar': 'cesar',
    'ang': 'angela', 'angie': 'angela',
    'tay': 'taylor',
    'des': 'destiny', 'desi': 'destiny',
    'sof': 'sofia', 'sofi': 'sofia',
    'vi': 'vivian',
    'greg': 'gregory',
    'jess': 'jessica',
    'gen': 'genevieve',
    'ver': 'veronica',
    'cor': 'corrina',
    'nat': 'natalie', 'natty': 'natalie',
}

FILLER_WORDS = {'both','always','honestly','really','slayed','literally','totally','especially',
                 'truly','basically','definitely','genuinely','obviously','clearly','actually',
                 'super','crushed','killed','rocked','nailed','went','she','he','they','was','is'}

def looks_like_a_name(s):
    if '!' in s or '+' in s or '?' in s or '%' in s or any(c.isdigit() for c in s):
        return False
    words = s.split()
    if len(words) == 0 or len(words) > 3:
        return False
    if any(w.lower() in FILLER_WORDS for w in words):
        return False
    return True

def resolve_nicknames(distinct_names):
    mapping = {}
    ambiguous = {}
    plausible_names = [n for n in distinct_names if looks_like_a_name(n)]
    for name in distinct_names:
        nl = name.lower()
        name_word_count = len(name.split())
        candidates = set()
        for other in plausible_names:
            ol = other.lower()
            if ol == nl or len(other) <= len(name):
                continue
            # only allow same word-count extensions (e.g. "Daph"->"Daphne", "Alex H"->"Alex Henry") --
            # adding a whole extra word (e.g. "Pauly"->"Pauly Mason") usually means two different
            # people whose names got run together in the source text, not one person's fuller name.
            if len(other.split()) != name_word_count:
                continue
            if ol.startswith(nl):
                candidates.add(other)
        if nl in COMMON_NICKNAMES:
            root = COMMON_NICKNAMES[nl]
            for other in plausible_names:
                if len(other.split()) == name_word_count and other.lower().startswith(root) and other.lower() != nl:
                    candidates.add(other)
        if len(candidates) == 1:
            mapping[name] = candidates.pop()
        elif len(candidates) > 1:
            ambiguous[name] = candidates
    return mapping, ambiguous

def apply_to_shop(json_path):
    with open(json_path) as f:
        records = json.load(f)
    distinct_names = set()
    for r in records:
        for m in r.get('namedMentions', []):
            distinct_names.add(m['name'])
    mapping, ambiguous = resolve_nicknames(list(distinct_names))
    if mapping:
        for r in records:
            for m in r.get('namedMentions', []):
                if m['name'] in mapping:
                    m['name'] = mapping[m['name']]
    with open(json_path, 'w') as f:
        json.dump(records, f, indent=2)
    return mapping, ambiguous

if __name__ == '__main__':
    shops = {
        'Antelope': 'antelope_records_full_window.json',
        'Fair Oaks': 'fairoaks_records_full_window.json',
        'Auburn': 'auburn_records_full_window.json',
        'Mad': 'madhouse_records_full_window.json',
        'Lichen': 'lichen_records_full_window.json',
        'Fireside': 'fireside_records_full_window.json',
        'Manz': 'manz_records_full_window.json',
    }
    for shop, path in shops.items():
        mapping, ambiguous = apply_to_shop(path)
        print(f'=== {shop} ===')
        if mapping:
            for short, full in mapping.items():
                print(f'  merged: {short!r} -> {full!r}')
        else:
            print('  no merges')
        if ambiguous:
            for short, cands in ambiguous.items():
                print(f'  SKIPPED (ambiguous): {short!r} could be {cands} -- left separate')
        print()
