#!/usr/bin/env python3
"""Rebuild the SKILL table that the forecast-accuracy panel reads.

Runs on a laptop, not in the browser and not on Pages: it fetches ~3.4 MB of
history, boils it down to ~6 KB of numbers, and rewrites the `const SKILL`
block inside index.html in place. The phone then needs no network call at all
to render the panel — which is the point, since the panel exists to be useful
during a dry spell when nothing recent can be scored.

    python3 build_skill.py            # fetch (cached), rewrite index.html
    python3 build_skill.py --print    # just show the tables, touch nothing

The table is stable — model ranking barely moves month to month — so monthly
or even seasonal reruns are plenty.

TRUTH is the Central Park ASOS hourly gauge via Iowa State's archive, which
reports 0.00 explicitly on dry hours. (api.weather.gov leaves those null, which
is what made the old panel fail.) report_type=3 selects the routine hourly
METAR; without it the "special" reports double-count the same accumulation.

FORECASTS come from two Open-Meteo archives that together give a lead ladder:
  L0  0-24 h out   historical-forecast-api, `precipitation`
  L1  24-48 h out  previous-runs-api, `precipitation_previous_day1`
  L2  48-72 h out  previous-runs-api, `precipitation_previous_day2`
HRRR has no L2 at all — that is past its forecast range, not a fetch bug.
"""

import argparse
import csv
import datetime as dt
import io
import json
import math
import pathlib
import statistics as st
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / '.skill-cache'
INDEX = HERE / 'index.html'

LAT, LON = 40.7644, -73.9594          # zip 10065, same point index.html uses
GAUGE = 'NYC'                          # Central Park ASOS, ~2 km from 10065
START = '2024-07-01'                   # earliest date all six models are complete
IN2MM = 25.4

# id -> display name. Order matters: the first three are the selectable models.
MODELS = [('gfs_hrrr', 'HRRR'), ('gfs_global', 'GFS'), ('ecmwf_ifs025', 'ECMWF'),
          ('icon_global', 'ICON'), ('gem_global', 'GEM'), ('jma_gsm', 'JMA')]
M3 = [m for m, _ in MODELS[:3]]
NAME = dict(MODELS)

# Storm definition, in gauge terms.
GAP_H = 6         # dry hours tolerated inside one storm
MIN_MM = 2.5      # 0.1 in - below this it is not a storm worth ranking models on
PAD_H = 3         # widen the window so a model that mistimes rain is charged for it

CAPE_CONV = 500   # J/kg, convective vs stratiform split
WARM = range(5, 11)   # May-Oct
SHRINK_K = 10     # slice means pulled toward the all-storm mean by n/(n+K)


# ----------------------------------------------------------------- fetching

def get(url, name):
    """Fetch with an on-disk cache so reruns and --print are instant."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / name
    if f.exists():
        return f.read_bytes()
    sys.stderr.write(f'  fetching {name} ...')
    sys.stderr.flush()
    req = urllib.request.Request(url, headers={'User-Agent': 'hrrr-skill-build'})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
    f.write_bytes(body)
    sys.stderr.write(f' {len(body)//1024} KB\n')
    return body


def om(host, extra, end):
    q = {'latitude': LAT, 'longitude': LON,
         'models': ','.join(m for m, _ in MODELS),
         'precipitation_unit': 'mm', 'timezone': 'UTC',
         'start_date': START, 'end_date': end}
    q.update(extra)
    return f'https://{host}/v1/forecast?' + urllib.parse.urlencode(q)


def load(end):
    """-> obs {hour -> mm}, fc {lead -> model -> {hour -> mm}}, cape {hour -> J/kg}"""
    y0, y1 = START[:4], end[:4]
    iem = ('https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?'
           f'station={GAUGE}&data=p01i&year1={y0}&month1={START[5:7]}&day1={START[8:10]}'
           f'&year2={y1}&month2={end[5:7]}&day2={end[8:10]}'
           '&tz=UTC&format=onlycomma&missing=empty&trace=0.0001&report_type=3')
    rows = csv.DictReader(io.StringIO(get(iem, f'gauge-{end}.csv').decode()))
    obs = {}
    for r in rows:
        v = r['p01i'].strip()
        if not v:
            continue
        # A METAR stamped ~HH:51 covers the hour ENDING ~(HH+1):00, which is also
        # Open-Meteo's convention (value at T = the hour ending at T).
        t = dt.datetime.strptime(r['valid'], '%Y-%m-%d %H:%M') + dt.timedelta(minutes=59)
        k = t.replace(minute=0, second=0).strftime('%Y-%m-%dT%H:%M')
        mm = float(v) * IN2MM
        obs[k] = max(obs.get(k, 0.0), 0.0 if mm < 0.05 else mm)   # trace -> dry

    hf = json.loads(get(om('historical-forecast-api.open-meteo.com',
                           {'hourly': 'precipitation,cape'}, end),
                        f'lead0-{end}.json'))['hourly']
    pr = json.loads(get(om('previous-runs-api.open-meteo.com',
                           {'hourly': 'precipitation_previous_day1,'
                                      'precipitation_previous_day2'}, end),
                        f'lead12-{end}.json'))['hourly']

    T = hf['time']
    ipr = {t: i for i, t in enumerate(pr['time'])}
    fc = {'L0': {}, 'L1': {}, 'L2': {}}
    for m, _ in MODELS:
        fc['L0'][m] = {t: hf['precipitation_' + m][i] for i, t in enumerate(T)}
        for lead, key in (('L1', 'precipitation_previous_day1_'),
                          ('L2', 'precipitation_previous_day2_')):
            col = pr[key + m]
            fc[lead][m] = {t: col[ipr[t]] for t in T if t in ipr}
    cape = {t: hf['cape_ecmwf_ifs025'][i] for i, t in enumerate(T)}
    return obs, fc, cape


# ----------------------------------------------------------------- scoring

def dice(f, o):
    """Sorensen-Dice overlap of two hourly rain series, 0-100.

    100 iff identical every hour; 0 iff no overlap at all (every rainy hour
    forecast dry and every forecast of rain landing on a dry hour). Scale-free,
    no tuned constant. index.html scores live series with the same formula.
    """
    den = sum(f) + sum(o)
    return None if den == 0 else 100 * 2 * sum(min(a, b) for a, b in zip(f, o)) / den


def storms(obs, fc, cape):
    """Cut the gauge record into storms and attach every model's forecast."""
    hours = sorted(obs)
    runs, cur, dry = [], [], 0
    for t in hours:
        if obs[t] > 0:
            cur.append(t)
            dry = 0
        elif cur:
            dry += 1
            cur.append(t)
            if dry > GAP_H:
                runs.append(cur[:-dry])
                cur, dry = [], 0
    if cur:
        runs.append(cur[:len(cur) - dry] if dry else cur)

    out = []
    for run in runs:
        if sum(obs[t] for t in run) < MIN_MM:
            continue
        a = dt.datetime.strptime(run[0], '%Y-%m-%dT%H:%M') - dt.timedelta(hours=PAD_H)
        b = dt.datetime.strptime(run[-1], '%Y-%m-%dT%H:%M') + dt.timedelta(hours=PAD_H)
        win, x = [], a
        while x <= b:
            win.append(x.strftime('%Y-%m-%dT%H:%M'))
            x += dt.timedelta(hours=1)
        if any(t not in obs for t in win):
            continue                       # gauge outage - drop rather than guess
        s = {'t0': a, 'o': [obs[t] for t in win], 'f': {},
             'cape': max(cape.get(t, 0) for t in win)}
        s['tot'] = sum(s['o'])
        for lead in ('L0', 'L1', 'L2'):
            s['f'][lead] = {m: [fc[lead][m][t] for t in win] for m, _ in MODELS
                            if all(fc[lead][m].get(t) is not None for t in win)}
        # Require the three selectable models at both leads the panel can use.
        if all(m in s['f']['L0'] and m in s['f']['L1'] for m in M3):
            out.append(s)
    out.sort(key=lambda s: s['t0'])
    return out


def blend(s, lead):
    """Equal-weight mean of whichever models are available at this lead.

    Deliberately plain: skill-weighting, in-storm reweighting, recency decay and
    fitted calibration were all backtested and all lost to this. See progress.md.
    """
    ms = [m for m, _ in MODELS if m in s['f'][lead]]
    return [st.mean(s['f'][lead][m][i] for m in ms) for i in range(len(s['o']))]


def mean_dice(group, lead, model):
    vals = []
    for s in group:
        f = blend(s, lead) if model == 'BLEND' else s['f'][lead].get(model)
        if f is None:
            continue
        d = dice(f, s['o'])
        if d is not None:
            vals.append(d)
    return round(st.mean(vals), 1) if vals else None


def slice_of(s):
    season = 'warm' if s['t0'].month in WARM else 'cool'
    return f"{season}_{'convective' if s['cape'] >= CAPE_CONV else 'stratiform'}"


def forecast_storms(obs, fc, lead):
    """Storms found in the FORECAST, which is the only thing the panel has.

    The ranking tables above are built from storms the gauge recorded - the
    standard way to ask "how well did each model capture real rain". But the
    amount and trust tables are read while looking at a forecast, so they have
    to be conditioned the same way: detect a storm exactly as the panel does at
    runtime, then look up what the gauge actually did. Conditioning those on
    observed storms instead silently drops every forecast that fizzled, and the
    resulting table told us to triple small forecasts - the opposite of right,
    because most small forecasts are not followed by much rain.

    Detection uses the three selectable models (always present); the reported
    total uses whatever wider blend the panel would display.
    """
    series = fc[lead]
    # Whichever of the selectable models exist at this lead: HRRR has no L2 at
    # all (past its forecast range), so requiring all three would find nothing.
    core = [m for m in M3 if any(v is not None for v in series[m].values())]
    if len(core) < 2:
        return []
    hours = sorted(t for t in series['ecmwf_ifs025']
                   if all(series[m].get(t) is not None for m in core))
    if not hours:
        return []
    trio = {t: st.mean(series[m][t] for m in core) for t in hours}

    runs, cur, dry = [], [], 0
    for t in hours:
        if trio[t] > 0.1:
            cur.append(t)
            dry = 0
        elif cur:
            dry += 1
            cur.append(t)
            if dry > 3:              # same gap tolerance the panel uses
                runs.append(cur[:-dry])
                cur, dry = [], 0
    if cur:
        runs.append(cur[:len(cur) - dry] if dry else cur)

    out = []
    for run in runs:
        if sum(trio[t] for t in run) < MIN_MM:
            continue
        a = dt.datetime.strptime(run[0], '%Y-%m-%dT%H:%M') - dt.timedelta(hours=PAD_H)
        b = dt.datetime.strptime(run[-1], '%Y-%m-%dT%H:%M') + dt.timedelta(hours=PAD_H)
        win, x = [], a
        while x <= b:
            win.append(x.strftime('%Y-%m-%dT%H:%M'))
            x += dt.timedelta(hours=1)
        if any(t not in obs for t in win):
            continue
        ms = [m for m, _ in MODELS if all(series[m].get(t) is not None for t in win)]
        if len(ms) < 3:
            continue
        f = sum(st.mean(series[m][t] for m in ms) for t in win)
        tots = [sum(series[m][t] for t in win) for m in core]
        out.append({
            'f': f,
            'o': sum(obs[t] for t in win),
            'cv': st.pstdev(tots) / st.mean(tots) if st.mean(tots) > 0 else 0.0,
        })
    return out


def outcome(part):
    """Summarise what actually fell for a group of forecast storms."""
    ratios = sorted(w['o'] / w['f'] for w in part if w['f'] > 0)
    real = [w for w in part if w['o'] >= 0.5]
    return {
        'n': len(part),
        # median observed/forecast: 1.0 = spot on, >1 = more rain than forecast
        'actual': round(st.median(ratios), 2) if ratios else None,
        'lo': round(ratios[len(ratios) // 10], 2) if ratios else None,
        'hi': round(ratios[9 * len(ratios) // 10], 2) if ratios else None,
        # median |forecast-actual|/actual, over storms that actually happened
        'err': round(100 * st.median(abs(w['f'] - w['o']) / w['o'] for w in real))
               if real else None,
        # how often the forecast storm produced essentially nothing
        'dud': round(1 - len(real) / len(part), 2) if part else None,
    }


# ----------------------------------------------------------------- the table

def build(all_storms, fcast):
    keys = [m for m, _ in MODELS[:3]] + ['BLEND']

    lead = {}
    for L in ('L0', 'L1', 'L2'):
        row = {}
        for k in keys:
            v = mean_dice(all_storms, L, k)
            if v is not None:
                row[NAME.get(k, k)] = v
        lead[L] = row

    slices = {}
    for name in ('cool_stratiform', 'cool_convective',
                 'warm_stratiform', 'warm_convective'):
        g = [s for s in all_storms if slice_of(s) == name]
        entry = {'n': len(g)}
        if g:
            # Shrink toward the all-storm value so a thin slice cannot reorder
            # the list on the strength of two or three storms.
            w = len(g) / (len(g) + SHRINK_K)
            for L in ('L0', 'L1', 'L2'):
                row = {}
                for k in keys:
                    disp = NAME.get(k, k)
                    v, base = mean_dice(g, L, k), lead[L].get(disp)
                    if v is None or base is None:
                        continue
                    row[disp] = round(w * v + (1 - w) * base, 1)
                if row:
                    entry[L] = row
        slices[name] = entry

    # What actually falls when the models forecast a storm of a given size.
    # Built from forecast-detected windows (see forecast_storms) so it is
    # conditioned on what the panel knows, not on what turned out to happen.
    amount = {}
    for L in ('L0', 'L1', 'L2'):
        g = sorted(fcast[L], key=lambda w: w['f'])
        if len(g) < 20:
            continue
        q = max(1, len(g) // 4)
        buckets = []
        for i in range(4):
            part = g[i * q:] if i == 3 else g[i * q:(i + 1) * q]
            if not part:
                continue
            b = outcome(part)
            b['maxIn'] = round(part[-1]['f'] / IN2MM, 2) if i < 3 else 99
            buckets.append(b)
        amount[L] = buckets

    # What each model is FOR: heaviest-hour timing, and how often an hour it
    # calls wet really is wet. A single ranking number hides both.
    timing = {}
    for L in ('L0', 'L1'):
        row = {}
        for m in M3:
            errs, hit, false_, miss = [], 0, 0, 0
            for s in all_storms:
                f = s['f'][L].get(m)
                if f is None:
                    continue
                if max(f) > 0:
                    errs.append(abs(f.index(max(f)) - s['o'].index(max(s['o']))))
                for a, b in zip(f, s['o']):
                    fw, ow = a >= 0.2, b >= 0.2
                    hit += fw and ow
                    false_ += fw and not ow
                    miss += ow and not fw
            if errs:
                row[NAME[m]] = {
                    'medH': round(st.median(errs), 1),
                    'within2': round(sum(e <= 2 for e in errs) / len(errs), 2),
                    'wetRight': round(hit / (hit + false_), 2) if hit + false_ else None,
                    'wetMissed': round(miss / (hit + miss), 2) if hit + miss else None,
                }
        timing[L] = row

    # Agreement -> how far off the total typically lands. The one signal that
    # genuinely varies storm to storm, so it drives the panel's trust line.
    # Also forecast-conditioned, for the same reason as `amount`.
    trust = {}
    for L in ('L0', 'L1', 'L2'):
        g = sorted(fcast[L], key=lambda w: w['cv'])
        if len(g) < 20:
            continue
        q = len(g) // 3
        bands = []
        for i in range(3):
            part = g[i * q:] if i == 2 else g[i * q:(i + 1) * q]
            b = outcome(part)
            b['cvMax'] = round(part[-1]['cv'], 2) if i < 2 else 99
            bands.append(b)
        trust[L] = bands

    return {
        'built': dt.date.today().isoformat(),
        'storms': len(all_storms),
        'fstorms': {L: len(v) for L, v in fcast.items()},
        'span': f"{all_storms[0]['t0'].date()}..{all_storms[-1]['t0'].date()}",
        'gauge': GAUGE,
        'lead': lead,
        'slices': slices,
        'amount': amount,
        'timing': timing,
        'trust': trust,
    }


# ----------------------------------------------------------------- output

BEGIN = '/* ===== SKILL TABLE — generated by build_skill.py, do not hand-edit ===== */'
END = '/* ===== end SKILL TABLE ===== */'


def render(skill):
    return (BEGIN + '\nconst SKILL = ' +
            json.dumps(skill, indent=1, sort_keys=False) + ';\n' + END)


def splice(skill):
    text = INDEX.read_text()
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        sys.exit(f'markers not found in {INDEX.name} — add {BEGIN} / {END} first')
    INDEX.write_text(text[:i] + render(skill) + text[j + len(END):])
    print(f'index.html: SKILL block rewritten '
          f'({skill["storms"]} storms, {skill["span"]})')


def report(skill):
    print(f'\n{skill["storms"]} storms  {skill["span"]}  gauge {skill["gauge"]}\n')
    names = ['HRRR', 'GFS', 'ECMWF', 'BLEND']
    print(f'{"":8s}' + ''.join(f'{n:>9s}' for n in names))
    for L, lbl in (('L0', '0-24h'), ('L1', '24-48h'), ('L2', '48-72h')):
        cells = ''.join(f'{skill["lead"][L].get(n, "-"):>9}' for n in names)
        print(f'{lbl:8s}{cells}')
    print('\nby storm type (shrunk toward the all-storm value):')
    for k, v in skill['slices'].items():
        if 'L1' in v:
            print(f'  {k:17s} n={v["n"]:3d}  ' +
                  '  '.join(f'{n} {v["L1"].get(n, "-")}' for n in names))
    print('\nwhen the models forecast a storm this big, what fell (0-24h):')
    print('   (actual = observed/forecast; 1.0 = spot on, >1 = more than forecast)')
    for b in skill['amount'].get('L0', []):
        print(f'  up to {b["maxIn"]:>5} in  n={b["n"]:3d}  actual {b["actual"]:.2f}x '
              f'(10-90: {b["lo"]}-{b["hi"]})  typical miss {b["err"]:3d}%  '
              f'fizzled {b["dud"]:.0%}')
    print('\ntrust bands by model agreement (0-24h):')
    for b in skill['trust'].get('L0', []):
        print(f'  spread<={b["cvMax"]:>5}  n={b["n"]:3d}  typical miss {b["err"]:3d}%'
              f'   actual {b["lo"]}-{b["hi"]}x forecast   fizzled {b["dud"]:.0%}')
    print('\nwhat each model is for (0-24h):')
    for n, t in skill['timing'].get('L0', {}).items():
        print(f'  {n:6s} heaviest hour off by {t["medH"]} h (within 2 h '
              f'{t["within2"]:.0%})   calls a wet hour right {t["wetRight"]:.0%}   '
              f'misses {t["wetMissed"]:.0%} of wet hours')
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--print', dest='dry', action='store_true',
                   help='show the tables without touching index.html')
    p.add_argument('--end', default=None, help='last day to include (YYYY-MM-DD)')
    a = p.parse_args()

    end = a.end or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    sys.stderr.write(f'building {START} .. {end}\n')
    obs, fc, cape = load(end)
    ss = storms(obs, fc, cape)
    if len(ss) < 40:
        sys.exit(f'only {len(ss)} storms found — refusing to write a thin table')
    fcast = {L: forecast_storms(obs, fc, L) for L in ('L0', 'L1', 'L2')}
    skill = build(ss, fcast)
    report(skill)
    if not a.dry:
        splice(skill)


if __name__ == '__main__':
    main()
