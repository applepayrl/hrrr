# progress.md — July 6 session

## 2026-07-21 (later) · CHANCE OF RAIN — the panel rebuild was mostly redundant

### User's verdict on the rebuild above
"This isn't really helpful — I can already see each of the 3 models by swiping,
and the 6-model blend by long-pressing." Correct. Of the panel shipped in 501a1c2,
the per-model amounts duplicated swipe, the blend duplicated long-press, and the
ranking bars are near-constant so they can't change a decision. Root cause: the
panel optimised the question "which model" AFTER the backtest had already shown
that question has no exploitable answer.

### What was actually missing: probability
Added the Open-Meteo ENSEMBLE api — ~120 runs of ECMWF(51) + GEFS(31) + ICON(40),
each started from a slightly nudged guess at the current state. 28-42 KB, ~0.6 s.
KEY POINT for future sessions: the ensemble is NOT a 4th model and NOT more
accurate. Its hourly AVERAGE is flat drizzle (runs disagree on timing, so
averaging smears one heavy hour into several light ones) and its storm total
matches the existing blend (7.7 vs 6.9 mm on the test case). Do NOT add it as a
4th cycle option — that was considered and rejected with data. Its whole value is
that counting wet runs gives a probability, which a single run cannot.
- models=ecmwf_ifs025,gfs025,icon_global → 122 series (119 members + 3 controls).
- icon_eu is silently IGNORED at this latitude (byte-identical response) — its
  grid stops short of NYC. Don't add it back.
- No historical ensemble archive exists (verified: returns all nulls), so none of
  this could be backtested at 10065. It is additive, not validated-better.

### Shipped
1. mm column now shows the chance of rain beneath the amount (`.cell-rain u`).
   Shown even when the selected model says 0.0 — that is the valuable case: HRRR
   read 0.0 all evening while 122 runs said 77/79/73%. Hidden below
   SHOW_CHANCE_PCT=20 so clear stretches stay clean. WET_MM=0.1 threshold.
2. Panel cut from ~270 lines to ~190 and reframed as odds: most likely total,
   10th-90th range, P(any rain), P(>0.2in), P(>1in). Removed per-model amounts,
   ranking bars, and the what-each-model-is-for paragraph. Historical ranking
   survives as a single footnote line.
3. PROB_URL fetch rides along in Promise.all but is allowed to fail — the table
   renders without it and the panel falls back to the backtested spread→error
   table (which needs no network). Verified both directions.

### Verified 2026-07-21 (local, 375x812)
- Per-hour percentages match hand-recomputation from raw members for 5 hours
  (77/70/67/78/79%), n=122.
- Storm odds match an independent recomputation on all 7 figures
  (mid 5.1, 10-90 1.7-16, any 99%, >0.2in 51%, >1in 3%).
- Ensemble endpoint stubbed to reject → table still renders, no percentages,
  panel falls back to the spread table, recovers on next refresh.
- No regressions: 6-model long-press data intact, cycling keeps percentages,
  radar/sat/swipe hooks present, zero mm-shown-without-wet-icon mismatches,
  zero console errors.
- Dry injected forecast → "No storm in the next 48 h. Every hour ahead is under
  15%." Never an error.

### Still not done
- Phase 2/3/4 from the plan (Fly, radar nowcast, MRMS truth) — untouched.
- build_skill.py + the SKILL table are still used, but only for the footnote and
  the offline fallback. If the ensemble proves reliable they could go entirely.

## 2026-07-21 · Accuracy panel REBUILD (storm-oriented) — IN PROGRESS

Plan: /Users/rlahoud/.claude/plans/when-i-press-the-spicy-seahorse.md (approved).
Analysis scripts: scratchpad analyze.py … analyze6.py (129 storms, 2 yrs, walk-forward).

### Why
Round-5's residual failure (line ~12 below) is now the DEFAULT experience: the panel
almost always says "couldn't score: no station reported enough of the past 24 h",
because api.weather.gov returns null precipitationLastHour on unreported hours and
KNYC is a co-op site. Worse, scoring "the last 24 h" can't answer the question the
user actually asks (which model to trust for an UPCOMING storm, usually checked
during a dry spell).

### Evidence that drives the design (all out-of-sample, 129 storms)
- Skill by lead (Dice): ECMWF 43.8/37.1/30.7, GFS 40.9/35.7/26.9, HRRR 36.1/26.0/none;
  BLEND6 47.0/41.2/36.1 (best everywhere). HRRR has NO data past 48 h.
- Ranking never flips: ECMWF ≥ GFS > HRRR in 11 of 12 slices.
- Under-prediction REVERSES with storm size (blend, 0-24h): 0.10-0.18in → 157% of
  actual; 0.18-0.36 → 104%; 0.36-0.88 → 73%; 0.92-2.62 → 65%. So NO flat multiplier.
- Model agreement is the one strong per-storm signal: agree → median total err 21%;
  diverge → 57%.
- HRRR is precise-but-shy (heaviest-hour median 1 h err, 70% within 2 h; "rain this
  hour" right 85%; but misses 43% of rain hours). ECMWF sensitive-but-noisy (misses
  12%, right 63%). → report AMOUNT from ECMWF/blend, TIMING from HRRR.
- SIX adaptive schemes tested, ALL lost to the plain equal-weight blend: recent form
  across storms; follow the in-storm leader after 6 h (35% vs 33% chance); rescale
  rest-of-storm by first-6h error (−1.2..−2.9); skill-weighted blend (−0.3/−0.9);
  fitted power-law calibration of totals (median err 32%→44%); season/regime
  conditioning. DESIGN RULE: more arithmetic on the same 3 numbers is a dead end.
  DO NOT reintroduce these.

### New data sources (verified live 2026-07-21, both CORS *)
- TRUTH: IEM ASOS mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=NYC&data=p01i
  → 8781 hourly rows/yr, ZERO blanks (0.00 explicit on dry hours). Use report_type=3
  (routine) — omitting it double-counts specials (LGA showed 10.87 in for one day).
  trace=0.0001 then floor <0.05 mm → 0.
- FORECAST HISTORY: historical-forecast-api = 0-24 h lead; previous-runs-api
  _previous_day1 = 24-48 h; _previous_day2 = 48-72 h (GFS/ECMWF only, HRRR all null).
  Both complete for all 6 models back to ~2024-07 (earlier = ECMWF missing).

### Scope decisions
- Phase 1 only (panel + build_skill.py). Phases 2-4 (Fly, radar nowcast, ensembles/
  MRMS) are in the plan but NOT being built now.
- SKILL table is INLINED into index.html between marker comments (not a separate
  skill.json) → zero network requests on panel open, works offline, no 404 mode.
- Script runs on the Mac at build time only. Table is stable (recency doesn't
  predict) → monthly/seasonal regeneration is plenty.
- NOT changing the main rain column's 6-model outlier-rejected mean: plain mean-6
  scored slightly better on 2 yrs, but the existing blend rests on a 2-5 yr backtest.

### CORRECTION found during implementation — "models run dry" was an ARTIFACT
The planned bias/"lean high" advice came from bucketing storms by what ACTUALLY
fell. That conditioning is unusable live (you don't know the outcome yet) AND it
inverts the answer: rebuilt on FORECAST-detected windows — the same detection the
panel runs at press time — the blend is roughly unbiased (median actual/forecast
0.86 / 0.76 / 1.02 / 1.08 across forecast-size quartiles). The old table would have
told the user to triple small forecasts; in reality 21% of small forecast storms
produce almost nothing. No multiplier is applied anywhere in the panel now.
Ranking tables still use gauge-detected storms (standard verification); amount +
trust tables use forecast-detected windows. See build_skill.py forecast_storms().

What the forecast-conditioned trust table actually says (0-24h):
  agree   (spread<=0.28) n=46  typical miss 21%  actual 0.68-1.54x  fizzled  0%
  mixed   (spread<=0.66) n=46  typical miss 39%  actual 0.22-1.90x  fizzled  2%
  diverge               n=46  typical miss 46%  actual 0.00-2.75x  fizzled 17%

### Files
- build_skill.py (new): fetches + caches to .skill-cache/ (gitignored), detects
  storms, scores, rewrites the `const SKILL` block in index.html between markers.
  `--print` shows tables without touching the file. Idempotent (verified).
- index.html: MAIN_URL gained `cape`; panel HTML shell simplified (h2#accTitle +
  #accBody + #accFoot); new .acc-when/.acc-trust/.acc-best/.acc-note/.acc-head/
  .acc-for CSS; SKILL block (~4.9 KB) + rewritten panel IIFE.

### Verified 2026-07-21 (local server, 375x812 mobile viewport)
20/20 injected-lastData assertions PASS, plus:
- A1 numbers match the standalone analysis exactly; rerun is byte-identical.
- A2 bone-dry 48 h → "No rain forecast in the next 48 h." + seasonal ranking,
  never an error. THIS WAS THE ORIGINAL BUG.
- A3 lead bucket flips exactly where startsIn crosses 24 h (swept 20-30 h).
  NOTE: window is anchored to the top of the current hour, so slot i is slightly
  under i hours away — slot 24 is correctly L0.
- A3b HRRR past its horizon → "no data", never a false 0 (was showing a bar).
- A4 slice + trust-band lookups match hand recomputation (agree cv=0.00 → 21%/n=46;
  diverge cv=1.14 → 46%/n=46).
- A5 live storm: HRRR 3.6 / GFS 7.9 / ECMWF 17.9 mm from the raw API == displayed;
  blend6 14.27 → "14 mm"; HRRR peak hour 21 == "Heaviest around 9 PM".
- A5b headline is the RAW blend at all three sizes; note follows the forecast-size
  bucket. No displayed number is ever multiplied.
- A7 zero console errors; cycleModel, long-press hook, __abortSwipe, radar
  open/close, satellite, 6-model ensemble cells all intact.
- A8 opening + re-rendering the panel issues ZERO network requests.
- A8b renders fully with fetch stubbed to reject (works offline).
- Fixed during testing: "starts in -1 h" → "under way now" for a storm already
  in progress.
- A8c (live Pages + phone) — pending push.

### Deviations from the approved plan
- L2 (48-72 h) is unreachable from the panel: the app fetches only 48 forecast
  hours, so a detected storm is always L0 or L1. The L2 columns are still built
  (free, and ready if the window is ever widened) but the panel never reads them.
- A6 (scoring-formula parity between index.html and build_skill.py) is moot: the
  panel no longer scores anything at runtime, it reads the table. A1 covers it.

### Status
- [x] 1 build_skill.py
- [x] 2 inline SKILL block + marker comments
- [x] 3 rewrite panel IIFE, add cape to MAIN_URL
- [x] 4 verify A1-A8b
- [x] 5 committed 501a1c2, pushed, Pages build triggered manually and confirmed
      `built 501a1c2`; live URL serves the SKILL table (129 storms) and the
      cape-bearing MAIN_URL. Remaining: open it on the actual phone (A8c).

### To regenerate the table later
`python3 build_skill.py` (add `--print` to preview). Rarely needed — the ranking
is stable, so monthly/seasonal is plenty. Re-fetches into .skill-cache/; delete
that directory to force fresh downloads. Then commit index.html and trigger the
Pages build manually (it still does not auto-build).

## ROUND 5 (fifth user message) — accuracy panel "no station reported enough" error
Diagnosis (live): required ≥20/24 hrs from one station anchored at its newest report; measured coverage KNYC 17/24, KJFK 14/24, KLGA 5/24, KEWR 4/24, KTEB 0/24 → none qualify → error. Causes: (1) threshold 20 > reality (best 17); (2) Central Park null-on-dry-hours; (3) high-freq stations (LGA/EWR) blow the 72-obs limit in ~5h; (4) TEB never reports precip. Sliding the window back 6h lifts KNYC to 20/24.
User chose: A+B (lower bar + slide + pick best-covered station), NOT composite/farther/coarser.
Implemented:
- ACC: minObsHours 20→12 (qualify), minHours 16→10 (score floor + fallback accept), maxSlideH=12.
- Refactored fetchObsWindow → stationBuckets() + bestWindow() (slides end back ≤maxSlideH to max coverage, ties→latest) + buildWin(). Selection: NEAREST station reaching minObsHours wins; else single best-covered station if ≥minHours; else null.
- fetchPrevRuns past_hours 30→48 (window can now end ≤12h before now → start ≈now−36h; 30h was too short and would null-out the earliest hours).
- Updated header comment + footer already shows "N h scored" and the actual window.
Verified live: KNYC selected, window slid to end Mon 22:00 local (Tue 02:00Z), 20 h scored, ECMWF 42 / GFS 39 / HRRR 26, no error, no console errors, swipe/cycle still fine.
Residual: on a bone-dry stretch where even KNYC+fallbacks report <10 non-null hrs it can still error; offered E (composite stations) as the next safeguard if it recurs.

## ROUND 4 (fourth user message)
Tasks: (1) make swipe FLUID (was choppy); (2) fix accuracy scoring — more spread, mathematically/empirically grounded, 0% only for total miss; (3) explain the 24h obs omissions + decide whether to revise the period.

### (1) Swipe — rewritten as a finger-tracking carousel
- #table wrapped in #pager. During a gesture, two "ghost" clone tables (prev+next model, painted via new renderModelInto()) are appended and translate WITH the finger so neighbours peek in; on release it settles one panel over (commit) or snaps back, via a single eased CSS transform transition (GPU translate3d).
- Axis lock (first 8px; horizontal only if |dx|>1.2|dy|) so vertical scroll stays native (passive touchmove until locked-horizontal, then preventDefault). Momentum: a fast flick commits even if short (vx>0.4 px/ms AND |dx|>30). Distance commit: |dx|>min(90, 0.28·W).
- CRITICAL fixes found via testing: (a) starting the slide via requestAnimationFrame failed when the tab wasn't painting → switched to forced reflow (void offsetWidth) + setTimeout(finalize) backstop so the commit ALWAYS lands; (b) velocity over sub-4ms dt blew up into bogus flicks → guard dt>4ms; (c) flick floor raised to |dx|>30 so a slow short drag snaps back.
- cycleModel() (title tap) now delegates to the same pager slide (installed as __cycleImpl; kept a hoisted global function cycleModel so the inline onclick still resolves).
- overflow:clip applied to #pager ONLY while .swiping (clip isn't a scroll container, and only-while-swiping keeps the sticky thead/day-dividers un-reanchored at rest). Verified sticky still works (thead stuck at y=55 while scrolled 600px).
- Verified: L/R cycle + wrap, short snap-back, vertical scroll ignored, mid-drag neighbour peek (screenshot), long-press still works, radar still opens, no console errors.

### (2) Accuracy — quantitative Sørensen–Dice similarity
- Replaced 100·e^(−MAE/0.5) with score = 100 · 2·Σmin(fᵢ,oᵢ) / Σ(fᵢ+oᵢ) over shared scored hours. = 1 − Bray–Curtis dissimilarity; standard hydrology rainfall-series similarity; PARAMETER-FREE (no tuned scale) and scale-free.
- Properties (verified with synthetic inputs): perfect→100; total miss (all rain, forecast 0)→0 EXACTLY the user's worst-case anchor; false alarm→0; 2× over→67; 3×→50; both-dry→null (shows —); <minHours→null.
- All 3 models scored on a COMMON hour mask (obs present AND all 3 forecasts present) → strictly apples-to-apples. Footer shows "N h scored" + formula.
- Live result now ECMWF 42 / GFS 39 / HRRR 24 (was 7/10/0) — spread + HRRR no longer 0 (it over-forecast 3×, real overlap credit). Manual recompute matched DOM exactly.

### (3) 24h obs omissions — explanation + decision (see final msg to user)
Cause: NWS METAR precipitationLastHour is null in hours where the station didn't encode a precip amount (trace/zero often omitted, esp. Central Park KNYC which is a limited co-op site, not a full ASOS), plus occasional missing hourly obs. Not an API-window issue (limit=72 covers >24h). Decision: KEEP 24h but (a) require ≥20/24 reported, (b) score all 3 models on the SAME present hours so omissions bias NONE of them and don't distort the ranking, (c) display the scored-hour count. Offered station-completeness alternative to user.

## ROUND 3 (third user message)
Tasks: (1) long-press card order fixed to HRRR,GFS,ECMWF,ICON,GEM,JMA (ENS_ORDER reordered); (2) accuracy panel now scores the past 24 OBSERVED hours (windowH=24, minObsHours=20, minHours=16), tolerating missing hourly reports (score only hours where BOTH obs and forecast exist); (3) swipe left/right anywhere on rows cycles the 3 active models — passive touch listeners on <main>, thresholds: <600ms, |dx|>60px, |dx|>2|dy|; swipe-left=next, swipe-right=prev; brief translateX+opacity slide via animateSwap; (4) app always opens on HRRR (modelIdx=0, dropped localStorage persistence); (5) app icon generated via PIL script (scratchpad/make_icon.py) → apple-touch-icon.png (512) + icon-180.png in project root; sun-behind-cloud + cyan raindrops on blue→navy gradient; wired into <head>.

Round-3 criteria:
- C22 long-press order == HRRR,GFS,ECMWF,ICON,GEM,JMA under every selected model.
- C23 accuracy window is 24 buckets; obsHours>=20; scoreModel skips hours missing on either side; footer shows 24h span + obsHours/24.
- C24 score math still 100·e^(−MAE/0.5) recomputed over the ~24 scored hours; matches manual.
- C25 swipe left advances model, swipe right reverses; small vertical drag does NOT trigger; wraps HRRR<->ECMWF.
- C26 fresh load (clear localStorage) opens on HRRR; after cycling + reload, still HRRR.
- C27 icon files exist, referenced in <head>, visually pleasant (manual image review — PASS, see screenshot).
- C9r2 no console errors.
Test: preview_eval simulated touch events on <main>; DOM/__acc checks; manual recompute.

Round-3 results (all PASS, live data):
- C22 order HRRR,GFS,ECMWF,ICON,GEM,JMA ✓. C26 fresh load (cleared localStorage) opens HRRR ✓.
- C25 swipe: left HRRR→GFS→ECMWF→HRRR(wrap), right reverses; vertical drag & short swipe no-op ✓.
- C23 window=24 buckets, obsHours 21/24, scoreModel skips hours null on either side ✓.
- C24 24h scores GFS 10 / ECMWF 7 / HRRR 0, exact manual match, sorted desc ✓. Alignment spot-checked hour-by-hour (obs total 23mm; HRRR run 67.9mm=big overpredict → genuine 0%, not a bug).
- C27 icon files present + linked in <head>; visual review good ✓. C9r2 no console errors ✓.

OPEN NOTE for user: 24h-lead scores come out low/clustered (0–10%) on rainy days with scaleMM=0.5 because 24h hourly QPF is genuinely poor (esp. HRRR). Ranking still discriminates. Offered to soften scale (e.g. 1.0mm) if more spread desired — NOT changed unilaterally (meets the spec: perfect=100%, monotonic).
- Round-3 committed + pushed; Pages build triggered manually.

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

## 2026-07-15 · GOES-19 satellite loop (cloud button)
Feature: full-screen GOES-19 GEOCOLOR loop (day true color / night IR), cropped to
NJ + southern NY + Long Island, last hour (~12 frames @5 min), stitched client-side
from 2400×2400 STAR CDN stills (pre-built site loop is only 600×600 → 4× sharper).
Cloud button (#satBtn, right:60px) next to radar button; X close; per-frame date+time
stamp pill; 60s HEAD-latest.jpg poll splices new frames in while open.

Key facts:
- CDN: https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/ne/GEOCOLOR/ — CORS `*` on
  images AND directory listing (~196 KB gzipped); filenames YYYYJJJHHMM_..._2400x2400.jpg
  (UTC, day-of-year); cadence ~5 min WITH GAPS → always parse listing, never predict names.
- Crop rect (2400-space): x=1130 y=920 w=620 h=580 — calibrated visually (Cape May,
  both LI forks, southern NY all in frame). Canvas backing = native 620×580.
- Title now abbreviates to "UES" under 430px viewport width (two right-side buttons
  would underlap "…Upper East Side" on phones); resize listener keeps it in sync.
- ~35 MB per cold open (user accepted; frames cached for the session, reopen instant).

Verified (all PASS): button layout clears longest title at 375px; 10 distinct frames
spanning 55 min; per-frame stamp lockstep (all frames); 2400×2400 source confirmed;
crop landmarks visible; close/reopen instant; live splice observed (new 20:16Z frame in,
oldest pruned); radar view regression-free; zero console errors.

Next: commit + push + MANUAL Pages build trigger (see IMPORTANT note above).

## 2026-07-15 · Sat loop v2: full-screen iPhone crop + cross-fade interpolation
- Crop now x=1130 y=536 w=620 h=1348 (2400-space): width unchanged, height extended
  N/S so 620:1348 exactly matches iPhone 17 Pro (402×874). Canvas is full-bleed via
  object-fit: cover (tiny trim on other aspect ratios, no letterbox anywhere).
- Playback rewritten from discrete setTimeout ticks to a rAF cross-fade: each frame
  linearly blends into the next over transMs=400ms, dwell 1500ms on newest, hard cut
  back to start (fading backwards would read as reversed motion). Stamp switches to
  the nearer frame at a=0.5.
- Verified: blend at a=0.5 == exact arithmetic midpoint at a max-motion pixel;
  backing 620×1348; fills 402×874 AND 375×812 viewports; stamp switch at halfway;
  close/reopen instant; zero console errors. NOTE: rAF is suspended in the hidden
  preview pane (document.hidden=true), so live playback can't be observed there —
  drive __sat.render(i,a) manually to test.

## 2026-07-15 · Sat loop v3: cross-fade reverted
User feedback: the cross-fade left ghosting traces and made the loop feel too slow.
Reverted playback to the discrete setTimeout tick engine (frameMs=180, dwell=1200);
KEPT the v2 full-screen crop (620×1348) + object-fit: cover. Comment in code marks
the cross-fade as tried-and-reverted so it isn't reintroduced.
Verified: tick advances with per-frame stamps (idx 1→6 over 4.5s in the throttled
hidden pane), stamp lockstep all 12 frames, close/reopen instant, zero console errors.

## 2026-07-15 · Swipe-back overlap fix, sat loop speed, stale-frame fix
1. SWIPE BUG (overlapping tables after a quick return-swipe): root cause reproduced —
   a background render() mid-drag (e.g. the refresh() fired by the previous settle)
   detaches the touch target; its touchend never bubbles to #pager (same iOS quirk as
   the long-press card), so the gesture never settles: ghosts freeze on screen, and
   the NEXT begin() orphaned them (refs overwritten). Fix: render() now calls
   window.__abortSwipe (abandon gesture, reset transform, sweep ghosts) next to
   __hideRainInfo; cleanup() is selector-based (ref-independent); begin() sweeps
   strays defensively. Repro test: mid-drag render + lift-on-detached-node → clean
   state (was: 2 stuck ghosts, frozen translate3d(120px), dragging pinned true).
2. SAT SPEED: frameMs 180 → 100 (~10 fps), same frames, no interpolation.
3. SAT STALE FRAMES ("Jul 15 4:21 PM · checked 7:56 PM"): two compounding defects —
   (a) load() had no network deadlines; a fetch stalled by iOS backgrounding never
   settles, `loading` latch pinned forever, every later load() no-ops while poll
   keeps updating "checked". Fix: fetchT AbortController deadlines (listing 20s,
   HEAD 10s), image-load timeout 30s, and a 90s watchdog on the loading latch.
   (b) poll() committed lastMod BEFORE load() succeeded, consuming the change on
   failure. Fix: commit only when load() returns success; verified failed load →
   next same-lm poll retries the listing (2 attempts vs old 1).
NOTE: sandbox proxy serves a frozen CDN listing (newest stayed 2021Z) — freshness
can only be end-to-end-verified on a real network; retry/timeout logic verified
deterministically via fetch stubs.

## 2026-07-15 · Stale sat frames root-caused: UPSTREAM GOES-19 OUTAGE + cache hardening
Investigation: user's frames pinned at 4:21 PM despite fixes. curl from local machine
(no browser/sandbox) proved the CDN itself has nothing newer: EVERY GOES-19 product
(ne, eus, full disk) stopped at 2020-2021Z while GOES-18 West is current → satellite
feed outage upstream. App was showing the newest frame in existence.
Hardening shipped anyway:
- listing fetch now cache:'no-store' (CDN sends invalid "cache-control: off" + no
  validators → browsers may heuristically cache the listing for hours);
- cross-check: if HEAD latest.jpg last-modified is >10 min newer than the newest
  listed key, refetch the listing once with a ?_=Date.now() cache-buster (verified
  via fetch stub: 2 listing calls, 2nd busted, all no-store);
- amber stamp badge when newest frame >30 min old: "NOAA feed delayed X h — showing
  latest available" (live-verified during the actual outage: "delayed 6.0 h").

## 2026-07-15 · GFS vs HRRR nighttime gap: VERIFIED REAL, not a bug
User saw GFS 30C/10mph vs HRRR 24C/1mph for 10-11p. Raw per-model Open-Meteo API
returns exactly those values (29.5C/10.1 vs 24.1C/1.4 → app rounds correctly);
cell_selection land/sea/nearest tested — land cell already used (elev 32m), not an
ocean-cell artifact. Genuine model disagreement (coarse 0.25° GFS vs 3km HRRR on a
heat-advection night). No code change.
