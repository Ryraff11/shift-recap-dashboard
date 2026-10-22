# shift-recap-dashboard

**Ops Hub** — a single-file dashboard for the DB Sac Dutch Bros stands, built from each
shop's shift-lead recap form, the Deputy shift-lead schedule, the HME drive-thru timer
reports and the Expired Product Log.

- Live site (GitHub Pages, public): https://ryraff11.github.io/shift-recap-dashboard/
- Daily Shop Pulse (yesterday per shop + upcoming Brew items): https://ryraff11.github.io/shift-recap-dashboard/pulse/
- Refresh: a Claude Routine runs `pipeline/refresh_dashboard.py` three times a day
  (1 AM / 1 PM / 7 PM Pacific), then pushes `index.html` and the data files to `main`.
  See `AUTOMATION.md`.

## Shops (9)

Antelope · Fair Oaks · Auburn · Mad (Madhouse) · Lichen · Fireside · Manz (Manzanita) · OV
(Orangevale) · Winding — these exact names are the keys used everywhere in the data.

## Data feed for other projects (`data/`)

Every refresh also writes a clean, machine-readable copy of the processed recap data,
committed to this repo so any other project can read it with a plain HTTPS fetch — no
auth, no API keys:

```
https://raw.githubusercontent.com/Ryraff11/shift-recap-dashboard/main/data/latest.json
https://raw.githubusercontent.com/Ryraff11/shift-recap-dashboard/main/data/daily/2026-10-21.json
```

- `data/latest.json` — the whole 60-day window: `{generatedAt, windowDays, shops, shifts, days:[…]}`,
  newest day first.
- `data/pulse.json` — the last 7 days only, same shape as latest.json (~0.5 MB; what the Daily Shop Pulse reads).
- `data/brew.json` — upcoming dated items from the latest Weekly Brew, summarized (source M.D.YY, items with date/end/title/kind); written by the refresh routine, read by the Pulse page.
- `data/daily/YYYY-MM-DD.json` — one day: `{generatedAt, date, shops: {<shop>: {Open, Mid, Close}}}`.
  Daily files are rewritten on every refresh for the days inside the window and left in
  place after they fall out of it.

Each shift slot looks like:

```json
{
  "status": "filed",
  "scheduledLead": "Carsen T.",
  "recaps": [
    {
      "submittedBy": "Carsen T.",
      "submittedAt": "2026-10-21T11:14:08",
      "late": false,
      "shiftFromSchedule": false,
      "flags": [{"kind": "good", "text": "…"}, {"kind": "bad", "text": "Hazard reported: …"}],
      "answers": {"<form question, verbatim>": "<full answer text>", "…": "…"}
    }
  ]
}
```

`status` is one of:

| status | meaning |
|---|---|
| `filed` | at least one recap arrived on time |
| `late` | recap(s) arrived, all after the shift's cutoff |
| `missing` | no recap and the window has closed |
| `pending` | today's shift, submission window still open |
| `untracked` | before the shop's go-live date (Winding started 2026-09-04) |
| `no-shift` | Deputy shows the slot unstaffed — nothing was expected |

`answers` carries **every non-empty answer on the form**, keyed by the question text as it
appears on the sheet (with the hand-written labels the dashboard uses for the common ones,
e.g. `Safety hazards`, `Tardy / early out`). Timestamps are store-local (Pacific).

### Privacy

The repo and the site are public, so names are shortened at build time: filers, scheduled
leads and crew named inside answers appear as `First L.`. Treat the free text as
operational notes about real people — don't republish it anywhere less private than here.

## Layout

```
index.html                          published dashboard (generated — do not edit)
pulse/index.html                    Daily Shop Pulse page (static; reads data/pulse.json, data/brew.json, pipeline/hme_timer_history.json)
data/                               machine-readable feed (generated each refresh)
pipeline/shift-recap-dashboard.html the dashboard template the pipeline fills in
pipeline/refresh_dashboard.py       orchestrator: builds all 9 shops, scrubs names, writes data/, injects index.html
pipeline/build_<shop>.py            per-shop recap parsers (one per form layout)
pipeline/shift_cutoffs.py           per-shop on-time cutoffs (single source of truth)
pipeline/parse_hme_email.py         HME report parser + the HME_SHOPS registry
pipeline/update_timer_history.py    accumulates HME timer history and injects the 60-day window
pipeline/hme_timer_history.json     committed timer history (never shrinks)
pipeline/deputy_schedule_history.json committed Deputy schedule history (never shrinks)
```
