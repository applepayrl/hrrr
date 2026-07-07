# progress.md — July 6 session

## ROUND 2 (second user message)
Tasks: (1) drop "blend on long-press" subtitle; (2) long-press card shows ALL 6 models + blend, confirm blend = average of 6 (finding: it's the mean of all 6 EXCEPT a wild-outlier top value >2×second+1mm is dropped — kept deliberately, disclosed to user); (3) drop rainfall lower-bound cutoffs (PRECIP_MIN removed; blank iff value rounds to 0.0); (4) icon rain state driven by the SAME rounded mm as the cell (fog exception); (5) info (ⓘ) button left of title → accuracy panel: HRRR/GFS/ECMWF scored 0–100% on past-6-observed-hours rain vs NWS obs (KNYC first, then LGA/JFK/EWR/TEB; most recent 6 consecutive reported hours), forecasts = previous_day1 runs (USER DECISION: 24h-ago runs, since no API serves 6h-ago runs), score = 100·e^(−MAE/0.5mm), sorted desc, X to close, background refresh 15 min + on open + on visibilitychange, footer shows obs window/station/basis/refreshed time.
Memory file radar-feature.md updated (30-min arrow, poll/stamp) with user permission.

Round-2 criteria:
- C12 subtitle: header reads "Updated h:mm" only.
- C13 long-press card lists all 6 models (ENS_ORDER) + Blend under every selected model.
- C14 blend math: card Blend == outlier-rejected mean recomputed manually from the 6 values.
- C15 no cutoff: cell blank ⇔ model mm rounds to 0.0; any 0.1+ displays.
- C16 icon⇔cell agreement for ALL rows × 3 models: number present ⇔ wet icon (rain/snow/thunder marks), fog exempt.
- C17 ⓘ opens panel, ✕ closes, returns to main screen.
- C18 scores sorted desc, each 0–100 or —; recomputed-by-hand pct matches for all 3 models.
- C19 footer shows obs window (start–end local), station id, 24h-run basis, refreshed time.
- C20 background: refreshAcc interval (15 min) registered at boot; refresh on visibilitychange.
- C21 obs window = 6 consecutive hourly buckets; METAR :51 report bucketed to ceil-hour (matches Open-Meteo hour-ending convention).
- C9r no console errors.
Test method: preview_eval against __acc hooks + DOM; manual recompute in eval.

Round-2 results (all PASS, live data):
- C12 "Updated 10:20 PM" only ✓. C13 all 6 names + Blend ✓. C14 card 0.1 mm == manual outlier-rejected mean ✓.
- C15/C16 swept ALL rows × 3 models: zero mismatches (HRRR 0 wet rows, GFS 12, ECMWF 14; number ⇔ wet icon everywhere) ✓.
- C17 open/✕ close ✓. C18 live scores ECMWF 39 / GFS 21 / HRRR 20, exact match to manual recompute, sorted desc ✓ (real rain evening: KNYC 0.5,0,0.8,1.3,1.3,0 mm).
- C19 foot: "Observed rain: 4:00 PM – 10:00 PM · station KNYC / run from ~24 h earlier / Score = 100·e^−MAE/0.5mm · Refreshed" ✓.
- C20 refreshAcc tick updates checkedAt, keeps rows; interval + visibilitychange wired at boot ✓. C21 six consecutive UTC hour keys ✓. C9r no console errors ✓.
- Round-2 committed + pushed; Pages build triggered manually (still doesn't auto-build).

Design notes round 2:
- Blend stays the OUTLIER-REJECTED mean (not plain average) — top value dropped only if > 2×second+1mm; disclosed to user.
- Wet-icon DOM detectors used in tests: rain stroke #38bdf8, snow stroke #f1f5f9, lightning #f59e0b, fog stroke #cbd5e1 (exempt).
- __acc debug hooks: refreshAcc, fetchObsWindow, fetchPrevRuns, scoreModel, last getter.

## Task list (from user)
0. Commit current state as "July 6 stable" → DONE as git tag `july-6-stable` (tree was clean; assumption flagged to user).
1. Confirm radar arrow direction = precip motion, length = 30-min drift distance.
2. Confirm radar background refresh; report refresh rate; ADD timestamp overlay (frame time + last-checked time).
3. Title click cycles HRRR → GFS → ECMWF; all row data (temp, icon, mm, wind) from selected model only; long-press card shows remaining models + blend.
4. Manhattan wind-grid offset (29°) must apply to whichever model is selected.
5. Publish to GitHub Pages (push to origin/main; Pages serves main@root → https://applepayrl.github.io/hrrr/).

## Key facts verified
- Open-Meteo multi-model request `models=gfs_hrrr,gfs_global,ecmwf_ifs025` returns ALL needed hourly vars for all 3 models, zero nulls (suffixes `_gfs_hrrr`, `_gfs_global`, `_ecmwf_ifs025`).
- Pages config: branch main, path /, status built.
- Radar arrow code (pre-existing): `estimateShift` returns (dx east+, dy south+) displacement; angle `atan2(dy,dx)` in screen coords = geographic motion direction; `projSec:1800` → 30-min drift; length px = projM / resMeters(displayZoom). Tip pinned at 10065. CORRECT by inspection; runtime test pending. Stale CSS comment "20-minute" → fix to 30.
- Radar does NOT currently auto-refresh while open (only on open + visibilitychange). Will add 60 s poll while radar view open & page visible.
- Preview sandbox gotcha (from memory): external tile hosts get one canned response each — tile-pixel analysis is garbage in preview; test arrow math deterministically via `window.__radar` hooks instead.

## Design decisions / assumptions
- Fetch strategy: ONE request for 3 full models + ONE precip-only request for JMA/ICON/GEM. Cycling re-renders from cache instantly AND kicks a background refresh().
- Ensemble stays 6-model (HRRR, GFS, JMA, ECMWF, ICON, GEM), blend shown only in long-press card.
- Row rain number = selected model's own precip (blank below PRECIP_MIN=0.15 but still long-pressable); color still = 6-model spread (assumption #2 to user).
- Long-press card = other 5 models + Blend (assumption #3 to user).
- Icon rain band + effectiveCloud precip override use selected model's precip; cloud covers / weather_code / is_day also from selected model.
- Wind: windIcon() already applies MANHATTAN_OFFSET to whatever direction it's given → passing selected model's wind_direction_10m satisfies task 4 automatically.
- Model selection persisted in localStorage key `model`; title text `<MODEL> · 10065 Upper East Side`; document.title updated too.
- Radar stamp: pill top-left "Radar h:mm · checked h:mm"; poll every 60 s; rebuild tile layer + arrow only when frame path changes, otherwise just update "checked".

## Falsifiable success criteria & test method
C1 estimateShift correctness: synthetic D×D masks shifted by known (dx,dy)=(3,-2) → returns exactly that. Test: preview_eval calling __radar.estimateShift. PASS/FAIL.
C2 drawArrow geometry: drawArrow(0°, 10000 m) → polygon tip x,y ≈ map.latLngToContainerPoint(COORDS) (±0.5 px); shaft length ≈ 10000/resMeters(zoom, 40.596) px (±1 px). Test: preview_eval DOM inspection.
C3 Radar stamp: after loadRadar, #radarStamp displays two h:mm times. Test: preview_eval textContent regex.
C4 Radar poll: with view open, interval registered (60 s); poll tick updates "checked" time. Test: call poll fn directly via debug hook, compare stamp text before/after (with mocked clock not needed — verify fetch called & stamp re-set).
C5 Model cycling: clicking title cycles text HRRR→GFS→ECMWF→HRRR and back to persisted value on reload. Test: preview_click ×3 + snapshot.
C6 Row data per model: first data row's temp/wind/mm equal the fetched JSON values for the selected model for that hour (temp rounded, wind rounded, mm 1-decimal or blank if <0.15). Test: preview_eval comparing DOM vs window-cached lastData for each of the 3 models.
C7 Wind offset: arrow rotation angle in first row's wind SVG == ((wd+180)%360 − 29 + 360)%360 for selected model. Test: preview_eval parse transform.
C8 Long-press card: shows exactly 5 model lines (excluding selected) + Blend line. Test: preview_eval invoking show() path via synthetic mousedown/hold or calling internals; verify box innerHTML.
C9 No console errors on load & after cycling. Test: preview_console_logs level=error.
C10 Publish: git push succeeds; https://applepayrl.github.io/hrrr/ serves new content (curl grep for new stamp element id after Pages build).

## Status
- [x] Tag july-6-stable
- [x] API/Pages verification
- [x] progress.md initial checkpoint
- [x] Implement radar stamp + 60s poll (task 2)
- [x] Implement model cycling (tasks 3+4)
- [x] Fix stale 20-min comment (task 1)
- [x] C1 estimateShift: synthetic (3,-2) recovered exactly, conf 1.0 — PASS
- [x] C2 drawArrow: tip == 10065 container point exactly; 10 km → 24.38 px == expected; 2nd angle 135° exact — PASS
- [x] C3 stamp: "Radar 5:50 PM · checked 5:55 PM" rendered — PASS
- [x] C4 poll: 60000 ms interval registered on open; same-frame poll leaves Leaflet layers untouched — PASS
- [x] C5 cycling: HRRR→GFS→ECMWF→HRRR, persisted to localStorage, document.title updates — PASS
- [x] C6 row data matches each model's raw JSON (temp/mm/wind speed) for all 3 models — PASS
- [x] C7 wind rotation == ((wd+180)%360 − 29 +360)%360 exactly, all 3 models — PASS
- [x] C8 long-press card: exactly the 5 non-selected models + Blend; verified for HRRR and GFS selected — PASS
- [x] C9 zero console errors after load + cycling — PASS
- [x] C11 (added mid-loop): mid-press table re-render dismisses card & cancels pending show timer — found real stuck-card bug, fixed by document-level release listeners + render() calling __hideRainInfo — PASS
- [x] Commit + push
- [x] C10 Pages deployment verified

## Notes for future sessions
- Long-press release listeners are on document (not #rows) AND render() force-hides the card: touchend on a node detached by re-render never bubbles (touch-event spec), which left the card stuck open.
- Known cosmetic quirk (pre-existing): hours with model precip 0.10–0.14 mm show a rain icon but a blank mm cell (rainBand wet ≥0.1 vs PRECIP_MIN display floor 0.15).
- loadRadar keeps a stale-but-stamped frame if a background poll fails; only first load shows "Radar unavailable".
- Preview sandbox: api.open-meteo.com AND api.rainviewer.com return real JSON; only map TILES are canned.
- IMPORTANT: GitHub Pages did NOT auto-build on push — latest build was stuck at 2d1bbbb (June 27), meaning the radar commit 5d42a7c was never live. Had to trigger manually: `gh api -X POST repos/applepayrl/hrrr/pages/builds`. Check build after every push: `gh api repos/applepayrl/hrrr/pages/builds/latest --jq '.status + " " + .commit'`.
