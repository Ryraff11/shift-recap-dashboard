"""Single source of truth for recap submission cutoffs — mirrors the dashboard's SHIFT_CUTOFFS.

Per-shop, store-local (Pacific) [hour, minute] deadlines used to mark a recap on-time vs late.
Open varies by weekday for every multi-time shop; Manz's Mid varies by weekday too; everything
else is a fixed tuple. Close times of (0, mm) are after midnight (the next calendar morning) --
each builder keeps its own after-midnight handling; this module only supplies the cutoff value.

Mid/Close here match every builder's prior hardcoded cutoffs, so only Open marking changes.
"""

# weekday index (dt.weekday(): Mon=0 .. Sun=6) -> key, locale-independent
_WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

SHIFT_CUTOFFS = {
    'Antelope': {
        'Open': {'Mon': (12, 15), 'Tue': (11, 30), 'Wed': (12, 15), 'Thu': (11, 30), 'Fri': (11, 30), 'Sat': (12, 15), 'Sun': (11, 30)},
        'Mid': (18, 15), 'Close': (23, 45),
    },
    'Fair Oaks': {
        'Open': {'Mon': (13, 0), 'Tue': (12, 30), 'Wed': (12, 30), 'Thu': (13, 0), 'Fri': (12, 30), 'Sat': (13, 0), 'Sun': (12, 30)},
        'Mid': (17, 45), 'Close': (23, 35),
    },
    'Auburn': {
        'Open': {'Mon': (12, 15), 'Tue': (12, 30), 'Wed': (12, 15), 'Thu': (12, 30), 'Fri': (12, 30), 'Sat': (12, 15), 'Sun': (12, 30)},
        'Mid': (18, 15), 'Close': (0, 20),
    },
    'Mad': {'Open': (12, 15), 'Mid': (17, 15), 'Close': (0, 15)},
    'Lichen': {
        'Open': {'Mon': (12, 15), 'Tue': (12, 30), 'Wed': (12, 15), 'Thu': (12, 30), 'Fri': (12, 15), 'Sat': (12, 30), 'Sun': (12, 30)},
        'Mid': (19, 15), 'Close': (0, 15),
    },
    'Fireside': {
        'Open': {'Mon': (12, 15), 'Tue': (11, 30), 'Wed': (12, 15), 'Thu': (11, 30), 'Fri': (11, 30), 'Sat': (12, 15), 'Sun': (12, 20)},
        'Mid': (18, 15), 'Close': (23, 15),
    },
    'OV': {
        'Open': {'Mon': (12, 0), 'Tue': (12, 30), 'Wed': (12, 0), 'Thu': (12, 30), 'Fri': (12, 30), 'Sat': (12, 0), 'Sun': (12, 30)},
        'Mid': (18, 15), 'Close': (23, 30),
    },
    'Manz': {
        'Open': {'Mon': (10, 45), 'Tue': (12, 30), 'Wed': (10, 45), 'Thu': (12, 30), 'Fri': (12, 30), 'Sat': (10, 45), 'Sun': (12, 30)},
        'Mid': {'Mon': (18, 15), 'Tue': (19, 15), 'Wed': (18, 15), 'Thu': (19, 15), 'Fri': (19, 15), 'Sat': (18, 15), 'Sun': (19, 15)},
        'Close': (23, 20),
    },
}

def cutoff_for(shop, shift, dt):
    """(hour, minute) cutoff for shop/shift given the submission datetime dt.

    Open and (for Manz) Mid are same-day submissions, so dt's weekday selects the right value;
    fixed tuples are returned as-is. Returns None for an unknown shop/shift."""
    conf = SHIFT_CUTOFFS.get(shop)
    if not conf:
        return None
    c = conf.get(shift)
    if c is None:
        return None
    if isinstance(c, tuple):
        return c
    return c.get(_WD[dt.weekday()])
