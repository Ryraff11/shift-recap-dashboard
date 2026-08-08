# Shift Recap Dashboard — Automation

This repo publishes a self-contained HTML dashboard to GitHub Pages
(`index.html` at the repo root → https://ryraff11.github.io/shift-recap-dashboard/).
The `pipeline/` folder holds the scripts that rebuild it from 7 Google Sheets.

## How a refresh works

1. Export the 7 "recap (Responses)" Google Sheets to CSV into `pipeline/`.
2. Run `python3 refresh_dashboard.py` from `pipeline/` — rebuilds all 7 shops and
   injects fresh data into `pipeline/shift-recap-dashboard.html`.
3. Copy that file to `index.html` at the repo root, restore the committed template
   so only `index.html` changes, then commit + push to `main`.

Raw CSV exports (`*_recap_raw.csv`) and intermediate JSON
(`*_records_full_window.json`) are git-ignored — they are regenerated every run
and must not be committed.

## Current schedule (interim)

A **self-bound Routine** (`trig_015FexUNUFjPY7yEMQP13JFJ`) fires the refresh 3×/day
**into the original chat session**. It works, but it is coupled to that conversation:
deleting that conversation orphans it (archiving is fine). This is the interim
setup — replace it with the native Routine below, then retire it.

## Target: fully-automated native Routine

Create this in the claude.ai **Routines** UI (the `/schedule` command). Unlike the
interim one, it spawns a **fresh session each run** and is independent of any chat.

- **Schedule:** three times daily — **1:00 AM, 1:00 PM, 7:00 PM**
- **Timezone:** **America/Los_Angeles** (local — the UI supports timezones, which
  also avoids daylight-saving drift)
- **Fresh session per run:** yes
- **Connector to attach:** **Google Drive** (required for the sheet exports).
  GitHub push needs no connector — it uses the account's GitHub connection, which
  already has write access.
- If the UI only accepts UTC cron, use `0 2,8,20 * * *` during PDT and
  `0 3,9,21 * * *` during PST.

### Task prompt to paste into the Routine

```
Automated refresh + publish of the Shift Recap Dashboard for the Ryraff11/shift-recap-dashboard repo. This is a fresh unattended session — run the whole task end to end, then stop. The pipeline scripts are ALREADY committed in the repo's pipeline/ folder — do NOT re-download them from Google Drive. Only the 9 Google Sheets change between runs.

STEP 1 — Repo on main, up to date. Locate the shift-recap-dashboard git repo in this session's workspace and cd into it. Run: git checkout main && git pull origin main. GitHub Pages serves main/root. The pipeline lives in pipeline/.

STEP 2 — Export the 9 Google Sheets to CSV into pipeline/, writing straight to disk. Do NOT load the full 1-1.6 MB exports into your context. Use the Google Drive tool mcp__Google_Drive__download_file_content with exportMimeType="text/csv". It returns JSON {content, id, mimeType, title} where content is base64; large results are auto-saved by the harness to a file path instead of inline — in EITHER case, decode the base64 to the target file with python3 (json.load the JSON, base64.b64decode the content field, write the bytes). Use these EXACT fileId -> filename mappings:
  1alTCXd3nBJe7GhhqBG2Uc5bhoRE7MfjWT5fkdbHZ9D0 -> pipeline/antelope_recap_raw.csv
  1DgYsLXsy0ClizmPON-H3wkrXkvS8Yoma0j85WfWMdkM -> pipeline/fairoaks_recap_raw.csv
  17SExtyyoc_a04-q9DAMvdmFLkMsnmBuy6f0jupW7ybo -> pipeline/auburn_recap_raw.csv
  1wUByNuv6QgeRkeeTReg15pmSMi6WyR32Rx-evHQ85LQ -> pipeline/madhouse_recap_raw.csv
  1r_lNJ89WAN82ilqD6IXd3iv4JvPIiOaJIquBcEJ5kMs -> pipeline/lichen_recap_raw.csv
  17cNKLcoUb8m00jsy53hJK9IKZQ8qSvq8onuBRNHG2rg -> pipeline/fireside_recap_raw.csv
  1KimjOrEDPa_eBawE-4ngZALlwIxdvVAtJubelCSNkhw -> pipeline/manz_recap_raw.csv
  1baOxs9v8nQg8GKXYFOUqGTmD0Z_ViRToaTBqYbkFTXs -> pipeline/ov_recap_raw.csv
  1UOubHMxyAfnUy30C7sqAOCW_GY-NaviWYqvdWPw7Xv0 -> pipeline/deputy_schedule_raw.csv
For the 8 *_recap_raw.csv files, verify each is non-empty and its first line is a Timestamp header row. For deputy_schedule_raw.csv (the Deputy shift-lead schedule — a different sheet shape), verify it is non-empty and its first line is a Date header row (Date,Shop,ShiftLabel,EmployeeName,EmployeeId,IsEmptySlot,ScheduledStart,ScheduledEnd). If any export fails or a file is empty, STOP and report (see STEP 6).

STEP 3 — Build. From the pipeline/ folder run: python3 refresh_dashboard.py. Confirm the output ends with "=== Done ===" and that all 8 shops built: Antelope, Fair Oaks, Auburn, Madhouse, Lichen, Fireside, Manz, OV. Capture each shop's "<N> <Shop> records built" count. If the run does not end with "=== Done ===" or any shop is missing/errors, STOP and report (see STEP 6).

STEP 4 — Publish to Pages. The build overwrote pipeline/shift-recap-dashboard.html with fresh data. Copy it to index.html at the repo root: cp pipeline/shift-recap-dashboard.html index.html. Then restore the committed template so only index.html changes in the diff: git checkout -- pipeline/shift-recap-dashboard.html. The *_recap_raw.csv and *_records_full_window.json files are gitignored — do NOT commit them; stage ONLY index.html. Set identity if unset: git config user.email noreply@anthropic.com && git config user.name Claude. Then: git add index.html && git commit -m "Automated dashboard refresh" && git push origin main (retry a failed push up to 4x with 2/4/8/16s backoff on NETWORK errors only). Confirm the push succeeded and note the commit SHA. If the push fails for a non-network reason (e.g. 403 permission), STOP and report (see STEP 6).

STEP 5 — Confirm live. Try to load https://ryraff11.github.io/shift-recap-dashboard/ (Pages may take a minute). Note: a sandbox's egress may block *.github.io with a 403 tunnel error — if you cannot reach it, say so and treat the successful push as the source of truth rather than retrying the fetch.

STEP 6 — Failure handling. Do NOT retry endlessly. On the FIRST hard failure of any step or any shop's build, stop and clearly report: which step and which shop failed, plus the full error output. Leave main untouched if the build didn't complete (only push a fully successful build).

FINAL REPORT (always): the per-shop record counts, the pushed commit SHA (or "no push — failed at step X"), and whether Pages was confirmed or unreachable-from-sandbox.
```

## After the native Routine runs successfully once

Delete the interim self-bound Routine so the dashboard isn't pushed twice:
`trig_015FexUNUFjPY7yEMQP13JFJ` (ask Claude, or remove it from the Routines UI).
