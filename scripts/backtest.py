#!/usr/bin/env python3
"""Replay the model over a finished season and score it against what happened.

    python scripts/backtest.py                 # 2025/26, GW6-38
    python scripts/backtest.py --from-gw 12
    python scripts/backtest.py --tune          # grid-search the fudge constants
    python scripts/backtest.py --components    # DefCon and minutes calibration

Until this has been run, the model's numbers are a reasoned guess. The point is
not to admire a correlation -- it is to answer three questions:

  1. Does the model beat naive baselines (FPL's own xP, points per game, price)?
     If not, it is not worth its complexity.
  2. Are the hand-picked constants (DC_DISPERSION, STRENGTH_K, APPEAR_UPLIFT)
     anywhere near right?
  3. Is it well calibrated, or only well ranked? Ranking drives transfers;
     calibration drives whether a -4 hit clears its threshold.

No lookahead: projecting gameweek N uses only rounds strictly before N, plus
the prior season. Getting this wrong is the classic way to build a backtest
that looks excellent and predicts nothing.

Data comes from github.com/vaastav/Fantasy-Premier-League. Fetch it with:
    scripts/fetch_history.sh
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict

from fpl_common import (
    APPEAR_UPLIFT,
    DATA,
    DC_DISPERSION,
    DC_THRESHOLD,
    HOME_ADV,
    LEAGUE_AVG_GOALS,
    clamp,
    fixture_points,
    nbinom_at_least,
    per90,
    poisson_at_least,
    safe_div,
)

HIST = DATA / "historical"
# vaastav writes goalkeepers as GK; the rest of the codebase uses GKP.
# Anything not listed here is skipped -- notably 2024/25's "AM" rows, the
# Assistant Manager chip. Those are managers, not footballers, and they score
# under entirely different rules.
POS_MAP = {"GK": "GKP", "GKP": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}
BLEND_MINUTES = 900.0  # ~10 full matches before this season displaces last

# Each season and the season before it, used for early-season blending.
SEASONS = {
    "2025-26": "2024-25",
    "2024-25": "2023-24",
}


def load_rows(path):
    if not path.exists():
        print(f"error: missing {path}\n  run: scripts/fetch_history.sh", file=sys.stderr)
        raise SystemExit(1)
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def num(row, key, default=0.0) -> float:
    try:
        return float(row.get(key) or default)
    except ValueError:
        return default


def prior_season_rates(season: str) -> dict[int, dict]:
    """Prior-season totals keyed by the persistent player code, for blending."""
    path = HIST / f"raw_{SEASONS[season]}.csv"
    prior = {int(float(r["code"])): r for r in load_rows(path) if r.get("code")}
    out = {}
    for code, row in prior.items():
        minutes = num(row, "minutes")
        if minutes <= 0:
            continue
        out[code] = {
            "minutes": minutes,
            "starts": num(row, "starts"),
            "xg": num(row, "expected_goals"),
            "xa": num(row, "expected_assists"),
            "dc": num(row, "defensive_contribution"),
            "saves": num(row, "saves"),
            "bonus": num(row, "bonus"),
            "yellow": num(row, "yellow_cards"),
            "points": num(row, "total_points"),
        }
    return out


def team_id_to_name(season: str) -> dict[str, str]:
    """merged_gw names the player's own team but gives the opponent as an id."""
    return {r["id"]: r["name"] for r in load_rows(HIST / f"teams_{season}.csv")}


def id_to_code(season: str) -> dict[int, int]:
    return {
        int(float(r["id"])): int(float(r["code"]))
        for r in load_rows(HIST / f"raw_{season}.csv")
        if r.get("id") and r.get("code")
    }


def spearman(xs, ys) -> float:
    """Rank correlation. For FPL, ordering matters more than absolute accuracy."""
    if len(xs) < 3:
        return float("nan")

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = shared
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num_ = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num_ / den if den else float("nan")


def build_state(rows_by_round, upto, prior, codes):
    """Cumulative player stats and team ratings using only rounds < `upto`."""
    cum = defaultdict(lambda: defaultdict(float))
    goals_for = defaultdict(float)
    goals_against = defaultdict(float)
    matches = defaultdict(float)
    seen_fixture = set()

    for rnd in range(1, upto):
        for row in rows_by_round.get(rnd, []):
            pid = int(float(row["element"]))
            cum[pid]["minutes"] += num(row, "minutes")
            cum[pid]["starts"] += num(row, "starts")
            cum[pid]["xg"] += num(row, "expected_goals")
            cum[pid]["xa"] += num(row, "expected_assists")
            cum[pid]["dc"] += num(row, "defensive_contribution")
            cum[pid]["saves"] += num(row, "saves")
            cum[pid]["bonus"] += num(row, "bonus")
            cum[pid]["yellow"] += num(row, "yellow_cards")
            cum[pid]["points"] += num(row, "total_points")
            cum[pid]["apps"] += 1 if num(row, "minutes") > 0 else 0

            # Team goals come off the fixture scoreline, counted once per fixture.
            key = (row.get("fixture"), row.get("team"))
            if key in seen_fixture or not row.get("fixture"):
                continue
            seen_fixture.add(key)
            home = str(row.get("was_home", "")).lower() == "true"
            hs, as_ = num(row, "team_h_score"), num(row, "team_a_score")
            team = row.get("team")
            goals_for[team] += hs if home else as_
            goals_against[team] += as_ if home else hs
            matches[team] += 1

    league_gpm = safe_div(sum(goals_for.values()), sum(matches.values()), LEAGUE_AVG_GOALS)
    ratings = {}
    for team in matches:
        played = matches[team]
        # Shrink toward the league mean early on, when a few matches prove little.
        weight = clamp(played / 8.0)
        att = safe_div(goals_for[team] / played, league_gpm, 1.0)
        dfn = safe_div(goals_against[team] / played, league_gpm, 1.0)
        ratings[team] = {
            "attack": 1 + weight * (att - 1),
            "defence": 1 + weight * (dfn - 1),
        }
    return cum, ratings, league_gpm


def blended_rates(pid, cum, prior, codes, rounds_elapsed):
    """Per-90 rates and a minutes model, blending season-to-date with 2024/25.

    `rounds_elapsed` must be every gameweek so far, NOT appearances. Dividing
    minutes by appearances gives minutes-per-appearance and quietly assumes the
    player starts every week, which inflates every rotated or injured player.
    project.py divides by the full 38 for exactly this reason.
    """
    cur = cum.get(pid, {})
    cur_min = cur.get("minutes", 0.0)
    past = prior.get(codes.get(pid, -1))

    if cur_min <= 0 and not past:
        return None
    if past and cur_min < BLEND_MINUTES:
        w = clamp(cur_min / BLEND_MINUTES)
        games_cur = max(rounds_elapsed, 1.0)
        merged = {
            "minutes": w * cur_min + (1 - w) * past["minutes"],
            "starts": w * cur.get("starts", 0.0) + (1 - w) * past["starts"],
            "xg": w * cur.get("xg", 0.0) + (1 - w) * past["xg"],
            "xa": w * cur.get("xa", 0.0) + (1 - w) * past["xa"],
            "dc": w * cur.get("dc", 0.0) + (1 - w) * past["dc"],
            "saves": w * cur.get("saves", 0.0) + (1 - w) * past["saves"],
            "bonus": w * cur.get("bonus", 0.0) + (1 - w) * past["bonus"],
            "yellow": w * cur.get("yellow", 0.0) + (1 - w) * past["yellow"],
            "points": w * cur.get("points", 0.0) + (1 - w) * past.get("points", 0.0),
            "games": w * games_cur + (1 - w) * 38.0,
        }
    else:
        merged = dict(cur)
        merged["games"] = max(rounds_elapsed, 1.0)
        merged.setdefault("minutes", cur_min)

    minutes = merged.get("minutes", 0.0)
    if minutes <= 0:
        return None
    games = max(merged.get("games", 1.0), 1.0)
    # Points per appearance, current season only. Blending this with last
    # season measurably hurts (rho 0.242 vs 0.359): recent scoring rate is the
    # single strongest signal and dilution wastes it. Falls back to the prior
    # season only when there is no current-season sample at all.
    if cur.get("apps", 0.0) > 0:
        ppg_current = safe_div(cur.get("points", 0.0), cur["apps"])
    elif past:
        ppg_current = safe_div(past.get("points", 0.0), 38.0)
    else:
        ppg_current = 0.0
    return {
        "rates": {
            "xg90": per90(merged.get("xg", 0.0), minutes),
            "xa90": per90(merged.get("xa", 0.0), minutes),
            "dc90": per90(merged.get("dc", 0.0), minutes),
            "sv90": per90(merged.get("saves", 0.0), minutes),
            "bonus90": per90(merged.get("bonus", 0.0), minutes),
            "yellow90": per90(merged.get("yellow", 0.0), minutes),
            "ppg": ppg_current,
        },
        # Kept separately as the naive baseline the model has to beat.
        "ppg": safe_div(cur.get("points", 0.0), max(cur.get("apps", 0.0), 1.0)),
        "p_start": clamp(safe_div(merged.get("starts", 0.0), games)),
        "xmins": safe_div(minutes, games),
        "pts90": per90(merged.get("points", 0.0), minutes),
    }


def team_baseline(ratings, team, league_gpm):
    """That team's average expected goals across a neutral schedule."""
    others = [t for t in ratings if t != team]
    if not others:
        return league_gpm
    total = 0.0
    for opp in others:
        home = league_gpm * HOME_ADV * ratings[team]["attack"] * ratings[opp]["defence"]
        away = league_gpm / HOME_ADV * ratings[team]["attack"] * ratings[opp]["defence"]
        total += (home + away) / 2
    return total / len(others)


def run(rows_by_round, prior, codes, team_names, from_gw, to_gw, dc_disp, appear_uplift):
    """Project every gameweek in range and pair each projection with the actual."""
    records = []
    for gw in range(from_gw, to_gw + 1):
        cum, ratings, league_gpm = build_state(rows_by_round, gw, prior, codes)
        if not ratings:
            continue
        baselines = {t: team_baseline(ratings, t, league_gpm) for t in ratings}

        for row in rows_by_round.get(gw, []):
            pid = int(float(row["element"]))
            pos = POS_MAP.get(row.get("position", ""))
            team, opp_id = row.get("team"), row.get("opponent_team")
            if pos is None or team not in ratings:
                continue

            model = blended_rates(pid, cum, prior, codes, gw - 1)
            if model is None:
                continue

            # opponent_team is an id, but `team` (and so `ratings`) is a name.
            opp_rating = ratings.get(team_names.get(opp_id, ""),
                                     {"attack": 1.0, "defence": 1.0})

            home = str(row.get("was_home", "")).lower() == "true"
            if home:
                xg_for = league_gpm * HOME_ADV * ratings[team]["attack"] * opp_rating["defence"]
                xg_against = league_gpm / HOME_ADV * opp_rating["attack"] * ratings[team]["defence"]
            else:
                xg_for = league_gpm / HOME_ADV * ratings[team]["attack"] * opp_rating["defence"]
                xg_against = league_gpm * HOME_ADV * opp_rating["attack"] * ratings[team]["defence"]

            p_start = model["p_start"]
            xp = fixture_points(
                pos, model["rates"], model["xmins"], p_start,
                clamp(p_start * appear_uplift), xg_for, xg_against,
                safe_div(xg_for, baselines.get(team, league_gpm), 1.0),
                dc_dispersion=dc_disp,
            )

            records.append({
                "gw": gw, "id": pid, "pos": pos, "name": row.get("name", ""),
                "xp": xp, "actual": num(row, "total_points"),
                "fpl_xp": num(row, "xP"), "ppg": model["ppg"],
                "price": num(row, "value"), "xmins": model["xmins"],
                "minutes": num(row, "minutes"),
                "dc": num(row, "defensive_contribution"),
                "dc90": model["rates"]["dc90"],
            })
    return records


def check_fpl_xp(records) -> str | None:
    """Flag a broken FPL xP column before it gets used as a baseline.

    The archived xP differs wildly in quality by season. In 2025/26 it averages
    0.26x actual points for players who actually played -- systematically about
    four times too low -- which tanks its correlation and makes our model look
    good by comparison. In 2024/25 it sits at 0.85x and is genuinely strong.
    A well-formed column should land near 1.0.
    """
    played = [r for r in records if r["minutes"] > 0]
    if not played:
        return None
    mean_xp = sum(r["fpl_xp"] for r in played) / len(played)
    mean_actual = sum(r["actual"] for r in played) / len(played)
    if mean_actual <= 0:
        return None
    ratio = mean_xp / mean_actual
    if not 0.6 <= ratio <= 1.4:
        return (f"FPL's xP column looks unreliable this season: it averages "
                f"{ratio:.2f}x actual points for players who played. Treat it as "
                "a broken baseline, not a beaten one.")
    return None


def score(records, label, key="xp"):
    if not records:
        return None
    pred = [r[key] for r in records]
    act = [r["actual"] for r in records]
    n = len(records)
    mae = sum(abs(p - a) for p, a in zip(pred, act)) / n
    rmse = math.sqrt(sum((p - a) ** 2 for p, a in zip(pred, act)) / n)
    bias = sum(pred) / n - sum(act) / n
    return {"label": label, "n": n, "mae": mae, "rmse": rmse,
            "rho": spearman(pred, act), "bias": bias}


def print_scores(scores):
    print(f"  {'model':<26}{'n':>7}{'rank rho':>10}{'MAE':>8}{'RMSE':>8}{'bias':>8}")
    for s in scores:
        if s:
            print(f"  {s['label']:<26}{s['n']:>7}{s['rho']:>10.3f}"
                  f"{s['mae']:>8.3f}{s['rmse']:>8.3f}{s['bias']:>+8.3f}")


def calibration(records, buckets=10):
    ranked = sorted(records, key=lambda r: r["xp"])
    size = max(1, len(ranked) // buckets)
    print(f"\n  {'decile':<8}{'mean xP':>10}{'mean actual':>14}{'n':>8}")
    for i in range(buckets):
        chunk = ranked[i * size:(i + 1) * size] if i < buckets - 1 else ranked[i * size:]
        if not chunk:
            continue
        mp = sum(r["xp"] for r in chunk) / len(chunk)
        ma = sum(r["actual"] for r in chunk) / len(chunk)
        flag = "  <-- over" if mp - ma > 0.5 else ("  <-- under" if ma - mp > 0.5 else "")
        print(f"  {i + 1:<8}{mp:>10.2f}{ma:>14.2f}{len(chunk):>8}{flag}")


def fit_defcon_shape(records):
    """Fit the negative-binomial shape by maximum likelihood on observed hits.

    Log-loss, not calibration-band error: bands are coarse and their sample
    sizes differ by two orders of magnitude, so fitting to them would let the
    3500-row low band dictate the answer for everyone.
    """
    rows = []
    for r in records:
        if r["pos"] not in DC_THRESHOLD or r["minutes"] < 60:
            continue
        lam = r["dc90"] * (r["minutes"] / 90.0)
        if lam <= 0:
            continue
        rows.append((DC_THRESHOLD[r["pos"]], lam,
                     1.0 if r["dc"] >= DC_THRESHOLD[r["pos"]] else 0.0))
    if not rows:
        return None, None

    def logloss(prob_fn):
        total = 0.0
        for k, lam, hit in rows:
            p = min(max(prob_fn(k, lam), 1e-6), 1 - 1e-6)
            total -= hit * math.log(p) + (1 - hit) * math.log(1 - p)
        return total / len(rows)

    poisson_ll = logloss(lambda k, lam: poisson_at_least(k, lam) * DC_DISPERSION)
    best = None
    for shape in (0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12, 20, 40):
        ll = logloss(lambda k, lam, s=shape: nbinom_at_least(k, lam, s))
        if best is None or ll < best[1]:
            best = (shape, ll)
    return (best, poisson_ll, len(rows))


def defcon_calibration(records):
    """Predicted P(hit threshold) vs the rate actually observed."""
    rows = [r for r in records if r["pos"] in DC_THRESHOLD and r["minutes"] >= 60]
    if not rows:
        print("  no eligible rows")
        return
    print(f"\n  DefCon: {len(rows)} player-gameweeks with 60+ minutes")
    print(f"  {'predicted P':<14}{'actual rate':>13}{'n':>8}")
    bands = [(0, .1), (.1, .25), (.25, .5), (.5, .75), (.75, .9), (.9, 1.01)]
    total_pred = total_act = 0.0
    for lo, hi in bands:
        chunk = []
        for r in rows:
            lam = r["dc90"] * (r["minutes"] / 90.0)
            p = poisson_at_least(DC_THRESHOLD[r["pos"]], lam)
            if lo <= p < hi:
                chunk.append((p, 1.0 if r["dc"] >= DC_THRESHOLD[r["pos"]] else 0.0))
        if not chunk:
            continue
        mp = sum(c[0] for c in chunk) / len(chunk)
        ma = sum(c[1] for c in chunk) / len(chunk)
        total_pred += sum(c[0] for c in chunk)
        total_act += sum(c[1] for c in chunk)
        print(f"  {lo:.2f}-{hi:<9.2f}{mp:>6.3f} -> {ma:>5.3f}{len(chunk):>8}")
    if total_pred:
        print(f"\n  implied DC_DISPERSION = {total_act / total_pred:.3f} "
              f"(currently {DC_DISPERSION})")


def minutes_calibration(records):
    rows = [r for r in records if r["xmins"] > 0]
    if not rows:
        return
    print(f"\n  Minutes: predicted vs actual over {len(rows)} player-gameweeks")
    print(f"  {'predicted xmins':<18}{'mean actual':>13}{'n':>8}")
    for lo, hi in [(0, 15), (15, 30), (30, 50), (50, 70), (70, 85), (85, 91)]:
        chunk = [r for r in rows if lo <= r["xmins"] < hi]
        if chunk:
            print(f"  {lo}-{hi:<15}{sum(r['minutes'] for r in chunk) / len(chunk):>13.1f}"
                  f"{len(chunk):>8}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2025-26", choices=sorted(SEASONS),
                        help="season to replay (default 2025-26)")
    parser.add_argument("--sweep-blend", action="store_true",
                        help="sweep FORM_BLEND -- use on a holdout season")
    parser.add_argument("--from-gw", type=int, default=6,
                        help="first gameweek to score (needs history before it)")
    parser.add_argument("--to-gw", type=int, default=38)
    parser.add_argument("--min-xmins", type=float, default=45.0,
                        help="only score players we would actually consider owning")
    parser.add_argument("--tune", action="store_true", help="grid-search constants")
    parser.add_argument("--components", action="store_true",
                        help="DefCon and minutes calibration detail")
    parser.add_argument("--fit-defcon", action="store_true",
                        help="fit the DefCon distribution by maximum likelihood")
    args = parser.parse_args()

    season = args.season
    merged = load_rows(HIST / f"merged_{season}.csv")
    rows_by_round = defaultdict(list)
    for row in merged:
        try:
            rows_by_round[int(float(row["round"]))].append(row)
        except (ValueError, KeyError):
            continue

    prior = prior_season_rates(season)
    codes = id_to_code(season)
    team_names = team_id_to_name(season)

    # DefCon only exists from 2025/26. Earlier seasons have no defensive stats
    # at all, so dc90 is 0 and the term contributes nothing. Report that
    # explicitly rather than letting a silently-absent component look like a
    # validated one.
    has_defcon = "defensive_contribution" in (merged[0] if merged else {})

    print(f"{season} backtest: GW{args.from_gw}-{args.to_gw}, "
          f"{len(merged)} player-gameweeks, "
          f"{len(prior)} players with {SEASONS[season]} history")
    if not has_defcon:
        print("  NOTE: this season has no defensive-contribution data (the rule did")
        print("        not exist). The DefCon term is inert -- these results say")
        print("        nothing about it, in either direction.")
    if season != "2025-26":
        print("  HOLDOUT: constants were tuned on 2025/26. Nothing here should be")
        print("           used to re-tune them, only to check whether they hold.")

    records = run(rows_by_round, prior, codes, team_names, args.from_gw, args.to_gw,
                  DC_DISPERSION, APPEAR_UPLIFT)
    considered = [r for r in records if r["xmins"] >= args.min_xmins]

    warning = check_fpl_xp(records)
    if warning:
        print(f"  DATA QUALITY: {warning}")

    print(f"\nAll players with a fixture ({len(records)} rows)")
    print_scores([
        score(records, "our model"),
        score(records, "FPL's own xP", "fpl_xp"),
        score(records, "points per game", "ppg"),
        score(records, "price", "price"),
    ])

    print(f"\nDecision-relevant: predicted {args.min_xmins:.0f}+ minutes ({len(considered)} rows)")
    print_scores([
        score(considered, "our model"),
        score(considered, "FPL's own xP", "fpl_xp"),
        score(considered, "points per game", "ppg"),
        score(considered, "price", "price"),
    ])

    print("\nCalibration (decision-relevant set)")
    calibration(considered)

    if args.components:
        print("\nComponent calibration")
        defcon_calibration(records)
        minutes_calibration(records)

    if args.fit_defcon:
        print("\nFitting the DefCon distribution (max likelihood)")
        fitted = fit_defcon_shape(records)
        if fitted[0]:
            (shape, ll), poisson_ll, n = fitted
            print(f"  {n} eligible player-gameweeks")
            print(f"  Poisson x {DC_DISPERSION}   log-loss {poisson_ll:.4f}")
            print(f"  NegBinom shape={shape:<5}  log-loss {ll:.4f}")
            better = (poisson_ll - ll) / poisson_ll * 100
            print(f"  negative binomial is {better:+.1f}% better")

    if args.sweep_blend:
        import fpl_common
        print(f"\nFORM_BLEND sweep ({len(considered)} decision-relevant rows)")
        print("  0.0 = structural model only, 1.0 = observed scoring rate only")
        print(f"  {'FORM_BLEND':<12}{'rho(all)':>10}{'rho(rel)':>10}{'RMSE':>8}{'bias':>8}")
        original = fpl_common.fixture_points
        best = None
        try:
            for weight in (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0):
                def patched(*a, _w=weight, **kw):
                    kw["form_blend"] = _w
                    return original(*a, **kw)
                globals()["fixture_points"] = patched
                recs = run(rows_by_round, prior, codes, team_names,
                           args.from_gw, args.to_gw, DC_DISPERSION, APPEAR_UPLIFT)
                subset = [r for r in recs if r["xmins"] >= args.min_xmins]
                sa, sr = score(recs, "all"), score(subset, "rel")
                if best is None or sr["rho"] > best[1]:
                    best = (weight, sr["rho"])
                print(f"  {weight:<12}{sa['rho']:>10.4f}{sr['rho']:>10.4f}"
                      f"{sr['rmse']:>8.3f}{sr['bias']:>+8.3f}")
        finally:
            globals()["fixture_points"] = original
        shipped = fpl_common.FORM_BLEND
        print(f"\n  best here: {best[0]}  (rho {best[1]:.4f})")
        print(f"  shipped:   {shipped}")
        if abs(best[0] - shipped) <= 0.2:
            print("  -> consistent with the tuned value; it generalises")
        else:
            print("  -> DIVERGES from the tuned value. Treat FORM_BLEND as overfitted")
            print("     to 2025/26 rather than re-tuning to this season.")

    if args.tune:
        print("\nGrid search (decision-relevant set, maximising rank correlation)")
        best = None
        for disp in (0.7, 0.8, 0.9, 1.0, 1.1):
            for uplift in (1.0, 1.15, 1.25, 1.4):
                recs = run(rows_by_round, prior, codes, team_names, args.from_gw,
                           args.to_gw, disp, uplift)
                subset = [r for r in recs if r["xmins"] >= args.min_xmins]
                s = score(subset, f"disp={disp} uplift={uplift}")
                if s and (best is None or s["rho"] > best[0]["rho"]):
                    best = (s, disp, uplift)
                print(f"  disp={disp:<5} uplift={uplift:<5} "
                      f"rho={s['rho']:.4f} rmse={s['rmse']:.3f} bias={s['bias']:+.3f}")
        if best:
            print(f"\n  best: DC_DISPERSION={best[1]}, APPEAR_UPLIFT={best[2]} "
                  f"(rho={best[0]['rho']:.4f})")
            print(f"  current: DC_DISPERSION={DC_DISPERSION}, APPEAR_UPLIFT={APPEAR_UPLIFT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
