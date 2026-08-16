#!/usr/bin/env python3
"""Expected-points model. Writes data/projections.{csv,json}.

    python scripts/project.py                  # next 5 gameweeks
    python scripts/project.py --horizon 8
    python scripts/project.py --from-gw 12
    python scripts/project.py --top 30         # print a leaderboard

Every number here is derived from cached API data. Nothing is recalled from
memory, and nothing is invented -- players with no usable history are emitted
with no_history=1 so they get reviewed by hand rather than silently ranked last.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict

from fpl_common import (
    APPEAR_UPLIFT,
    ASSUMED_DISCOUNT,
    DATA,
    HOME_ADV,
    LEAGUE_AVG_GOALS,
    POS,
    STATE,
    STRENGTH_K,
    FetchError,
    clamp,
    fixture_points,
    fmt_price,
    load_bootstrap,
    load_fixtures,
    load_summary,
    next_event,
    per90,
    poisson_at_least,
    safe_div,
)

def team_ratings(bootstrap: dict) -> tuple[dict[int, dict], str]:
    """Attack/defence multipliers per team, from the best signal available.

    In preseason strength_attack_* and strength_defence_* are all zero, so this
    falls back to the 1-5 strength_overall_* ratings and says so -- the caller
    reports the degraded source rather than presenting equal confidence.
    """
    teams = bootstrap["teams"]
    detailed = any(t.get("strength_attack_home") for t in teams)
    source = "strength_attack/defence" if detailed else "strength_overall (preseason fallback)"

    ratings: dict[int, dict] = {}
    if detailed:
        att = [t["strength_attack_home"] + t["strength_attack_away"] for t in teams]
        dfn = [t["strength_defence_home"] + t["strength_defence_away"] for t in teams]
        att_mean, dfn_mean = sum(att) / len(att), sum(dfn) / len(dfn)
        for team in teams:
            a = safe_div(team["strength_attack_home"] + team["strength_attack_away"], att_mean, 1.0)
            # Both multipliers scale the OPPONENT's expected goals, so defence
            # must be inverted: a higher strength_defence means a better defence,
            # which should concede fewer goals, not more.
            d = safe_div(dfn_mean, team["strength_defence_home"] + team["strength_defence_away"], 1.0)
            ratings[team["id"]] = {"attack": a, "defence": d, "short": team["short_name"]}
    else:
        for team in teams:
            s = (team.get("strength_overall_home", 3) + team.get("strength_overall_away", 3)) / 2
            ratings[team["id"]] = {
                # Better teams score more and concede less, hence the sign flip.
                "attack": 1 + STRENGTH_K * (s - 3) / 2,
                "defence": 1 - STRENGTH_K * (s - 3) / 2,
                "short": team["short_name"],
            }
    return ratings, source


def fixture_goals(ratings: dict, home_id: int, away_id: int) -> tuple[float, float]:
    """Expected goals for (home, away) in one fixture."""
    home = LEAGUE_AVG_GOALS * HOME_ADV * ratings[home_id]["attack"] * ratings[away_id]["defence"]
    away = LEAGUE_AVG_GOALS / HOME_ADV * ratings[away_id]["attack"] * ratings[home_id]["defence"]
    return home, away


def baseline_goals(ratings: dict) -> dict[int, float]:
    """Each team's average expected goals per match across a neutral schedule.

    Player scoring rates already embed their team's typical output, so fixture
    adjustment must be relative to this baseline, not to the league average --
    otherwise good teams get their quality counted twice.
    """
    ids = list(ratings)
    out: dict[int, float] = {}
    for tid in ids:
        total = 0.0
        for oid in ids:
            if oid == tid:
                continue
            h, _ = fixture_goals(ratings, tid, oid)
            _, a = fixture_goals(ratings, oid, tid)
            total += (h + a) / 2
        out[tid] = safe_div(total, len(ids) - 1, LEAGUE_AVG_GOALS)
    return out


def source_season(element: dict, summary: dict | None) -> tuple[dict, str]:
    """Pick the stat line to model from, blending current season once it matures.

    Preseason every current-season field is zero, so this falls back to the most
    recent history_past entry. That is the whole reason draft mode works at all.
    """
    cur_min = float(element.get("minutes") or 0)
    past = (summary or {}).get("history_past") or []
    last = past[-1] if past else None

    current = {
        "minutes": cur_min,
        "starts": float(element.get("starts") or 0),
        "expected_goals": float(element.get("expected_goals") or 0),
        "expected_assists": float(element.get("expected_assists") or 0),
        "defensive_contribution": float(element.get("defensive_contribution") or 0),
        "saves": float(element.get("saves") or 0),
        "bonus": float(element.get("bonus") or 0),
        "yellow_cards": float(element.get("yellow_cards") or 0),
        "total_points": float(element.get("total_points") or 0),
        "games": 38.0,
    }

    if last is None:
        return current, ("current" if cur_min > 0 else "none")
    prior = {
        "minutes": float(last.get("minutes") or 0),
        "starts": float(last.get("starts") or 0),
        "expected_goals": float(last.get("expected_goals") or 0),
        "expected_assists": float(last.get("expected_assists") or 0),
        "defensive_contribution": float(last.get("defensive_contribution") or 0),
        "saves": float(last.get("saves") or 0),
        "bonus": float(last.get("bonus") or 0),
        "yellow_cards": float(last.get("yellow_cards") or 0),
        "total_points": float(last.get("total_points") or 0),
        "games": 38.0,
    }
    if cur_min <= 0:
        return prior, f"history:{last.get('season_name')}"

    # Trust this season once there is a meaningful sample (~10 full matches).
    w = clamp(cur_min / 900.0)
    blended = {k: w * current[k] + (1 - w) * prior[k] for k in prior if k != "games"}
    blended["games"] = 38.0
    return blended, f"blend:{w:.2f}"


def availability(element: dict) -> float:
    status = element.get("status", "a")
    if status == "a":
        chance = element.get("chance_of_playing_next_round")
        return 1.0 if chance is None else clamp(chance / 100.0)
    if status == "d":
        chance = element.get("chance_of_playing_next_round")
        return clamp(0.5 if chance is None else chance / 100.0)
    return 0.0  # i (injured), s (suspended), u (unavailable), n (not in squad)


def load_odds_map() -> dict[int, tuple[float, float]]:
    """fixture id -> (xG home, xG away) from bookmaker prices, when available.

    Odds beat any model we can build, so where they exist they replace the
    strength calculation entirely rather than being blended with it.
    """
    path = DATA / "odds.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {r["fixture"]: (r["xg_h"], r["xg_a"]) for r in payload.get("fixtures", [])}


def replacement_rates(bootstrap, load) -> dict[str, dict]:
    """Median per-90 rates by position among established regular starters.

    This is what a player "of that position who plays" typically produces. It
    stands in for players with no usable Premier League history -- promoted
    clubs and new signings -- who otherwise project at zero and are invisible
    to the optimiser.

    Deliberately NOT scaled by any blanket promoted-club constant. Measured
    across two promoted cohorts, the discount ranges 0.47-1.00 for defenders
    and tracks the team's goals conceded almost exactly, because defender
    points are mostly clean sheets. Team quality is already modelled downstream
    via expected goals for and against, so a constant here would double-count
    it. Only the attacking rates get a team scaling, applied by the caller.
    """
    buckets: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for element in bootstrap["elements"]:
        stats, _ = source_season(element, load(element["id"]))
        minutes = stats["minutes"]
        if minutes < 900:  # regular starters only -- this is a "if he plays" rate
            continue
        pos = POS[element["element_type"]]
        for key, field in (("xg90", "expected_goals"), ("xa90", "expected_assists"),
                           ("dc90", "defensive_contribution"), ("sv90", "saves"),
                           ("bonus90", "bonus"), ("yellow90", "yellow_cards")):
            buckets[pos][key].append(per90(stats[field], minutes))
        # Points per gameweek too, so assumed players still get shrunk by the
        # form blend. Without it they skip that shrinkage entirely and, since
        # the structural model over-predicts, end up out-projecting comparable
        # established players -- a Coventry forward beating a Bournemouth one.
        # Points per MINUTE, not per gameweek. Per-gameweek would need dividing
        # by a reference minutes figure, and since each median is taken over a
        # different player that ratio is meaningless -- it inflated an 80-minute
        # assumption by 30%. Per-minute multiplies cleanly by asserted minutes.
        buckets[pos]["pts_per_min"].append(safe_div(stats["total_points"], minutes))

    out = {}
    for pos, rates in buckets.items():
        out[pos] = {k: statistics.median(v) if v else 0.0 for k, v in rates.items()}
    return out


def load_assumptions() -> dict:
    """Human-asserted minutes for players the data cannot model.

    A projection for a promoted-club player is only produced when someone has
    explicitly asserted that he plays. FPL's own preseason pricing correlates
    with eventual minutes at just rho 0.175 for these players, so there is no
    data-driven shortcut -- and inventing one would break the rule that every
    number traces back to evidence.
    """
    path = STATE / "minutes-assumptions.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"warning: {path} is not valid JSON -- ignoring", file=sys.stderr)
        return {}
    out = {}
    for entry in payload.get("assumptions", []):
        if "id" in entry:
            out[int(entry["id"])] = entry
    return out


# A player who joined after the last completed season ended has NO record at
# his current club: every minute, goal and defensive action in history_past was
# earned elsewhere. Team context (fixtures, clean-sheet odds) correctly uses the
# new club, and his personal per-90 rates travel with him -- but p_start does
# not. Starting 34 games at a mid-table side says little about starting for a
# title contender. Preseason this affects a large share of the highest-rated
# players, so it is flagged rather than silently trusted.
NEW_CLUB_CUTOFF = "2026-06-01"


def joined_new_club(element: dict, cutoff: str = NEW_CLUB_CUTOFF) -> bool:
    joined = element.get("team_join_date")
    return bool(joined and joined >= cutoff)


def stale_source(src: str, newest_season: str) -> bool:
    """True when a player's most recent PL season is not the latest one."""
    return bool(src.startswith("history:") and newest_season
                and not src.endswith(newest_season))


def latest_season(bootstrap, load) -> str:
    """The most recent season any player has history for.

    Used to spot players whose data is years out of date rather than merely
    last season's -- see `stale` in project_player.
    """
    seen = set()
    for element in bootstrap["elements"]:
        for past in (load(element["id"]) or {}).get("history_past") or []:
            if past.get("season_name"):
                seen.add(past["season_name"])
    return max(seen) if seen else ""


def project_player(element, summary, ratings, baselines, fixtures_by_team, gws,
                   odds_map=None, newest_season="", replacement=None, assumptions=None):
    pos = POS[element["element_type"]]
    stats, src = source_season(element, summary)
    avail = availability(element)

    minutes = stats["minutes"]
    starts = stats["starts"]
    no_history = minutes < 180  # under two full matches is not a usable sample

    # --- minutes model ---
    p_start = clamp(safe_div(starts, stats["games"]))
    p_start *= avail
    xmins = safe_div(minutes, stats["games"]) * avail
    p_appear = clamp(p_start * APPEAR_UPLIFT)

    # A player with no usable history is projected only when a human has
    # asserted he plays. Without that assertion he stays at zero and the
    # optimiser ignores him, which is the honest default: we genuinely do not
    # know whether Coventry's left-back is first choice.
    assumption = (assumptions or {}).get(element["id"])
    assumed = 0
    if assumption and (no_history or stale_source(src, newest_season)) and avail > 0:
        assumed = 1
        xmins = float(assumption.get("xmins", 0)) * avail
        p_start = clamp(float(assumption.get("p_start", xmins / 90.0))) * avail
        p_appear = clamp(p_start * APPEAR_UPLIFT)

    # --- per-90 rates ---
    rates = {
        "xg90": per90(stats["expected_goals"], minutes),
        "xa90": per90(stats["expected_assists"], minutes),
        "dc90": per90(stats["defensive_contribution"], minutes),
        "sv90": per90(stats["saves"], minutes),
        "bonus90": per90(stats["bonus"], minutes),
        "yellow90": per90(stats["yellow_cards"], minutes),
        # Expected points per gameweek from observed scoring, averaged over the
        # whole season so missed games are already discounted. fixture_points
        # blends this with the structural model -- see FORM_BLEND.
        "ppg": safe_div(stats["total_points"], stats["games"]),
    }

    if assumed:
        # Substitute replacement-level rates for a player we have no sample for.
        # Attacking output is scaled by the team's attack rating, since the
        # median is drawn from league-wide starters and would otherwise credit
        # a promoted-club forward with mid-table service. Clean sheets and
        # goals conceded need no adjustment -- they already come from this
        # team's expected goals against.
        base = (replacement or {}).get(pos, {})
        rating = ratings[element["team"]]
        attack = rating["attack"]
        rates = dict(base)
        rates["xg90"] = base.get("xg90", 0.0) * attack
        rates["xa90"] = base.get("xa90", 0.0) * attack
        # Scale the baseline by the side of the team that drives this position's
        # points: attack for forwards and midfielders, defensive solidity for
        # defenders and keepers. That matches the measurement -- promoted-club
        # defender returns tracked goals conceded almost exactly (Sunderland
        # 1.26 GA/game -> 1.00 ratio, Ipswich 2.16 -> 0.47).
        team_factor = attack if pos in ("MID", "FWD") else safe_div(1.0, rating["defence"], 1.0)
        rates["ppg"] = base.get("pts_per_min", 0.0) * xmins * team_factor
        for key in ("xg90", "xa90", "dc90", "bonus90", "ppg"):
            rates[key] = rates.get(key, 0.0) * ASSUMED_DISCOUNT

    team_id = element["team"]
    base_xg = baselines.get(team_id, LEAGUE_AVG_GOALS)

    per_gw: dict[int, float] = {}
    per_gw_components: dict[int, dict[str, float]] = {}
    component_totals = {
        "appearance": 0.0,
        "goals": 0.0,
        "assists": 0.0,
        "clean_sheet": 0.0,
        "concede_penalty": 0.0,
        "saves": 0.0,
        "defcon": 0.0,
        "bonus": 0.0,
        "cards": 0.0,
        "observed": 0.0,
        "structural": 0.0,
    }
    fixture_count = 0
    for gw in gws:
        total = 0.0
        gw_components = dict.fromkeys(component_totals, 0.0)
        for fixture in fixtures_by_team.get(team_id, {}).get(gw, []):
            fixture_count += 1
            is_home = fixture["team_h"] == team_id
            priced = (odds_map or {}).get(fixture["id"])
            if priced:
                xg_h, xg_a = priced
            else:
                xg_h, xg_a = fixture_goals(ratings, fixture["team_h"], fixture["team_a"])
            xg_for, xg_against = (xg_h, xg_a) if is_home else (xg_a, xg_h)
            parts = fixture_points(
                pos, rates, xmins, p_start, p_appear,
                xg_for, xg_against, safe_div(xg_for, base_xg, 1.0),
                avail=avail, components=True)
            total += parts["total"]
            for key in gw_components:
                gw_components[key] += parts[key]
        per_gw[gw] = round(total, 3)
        per_gw_components[gw] = {key: round(value, 3) for key, value in gw_components.items()}
        for key, value in gw_components.items():
            component_totals[key] += value

    horizon = round(sum(per_gw.values()), 3)
    component_totals = {key: round(value, 3) for key, value in component_totals.items()}

    # The naive baseline, carried alongside the projection on purpose. Across
    # both backtested seasons it out-ranks the model by 0.04-0.06 rho, so it is
    # not a footnote -- it is the number the model has to justify departing
    # from. `xp_edge` is that departure: strongly positive means the model sees
    # something the scoring record does not (kind fixtures, a double, rising
    # minutes); strongly negative means it is fading a proven scorer, which is
    # worth a second look before acting on it.
    # None for assumed players: there is no observed scoring record, so the
    # form blend is skipped and the baseline column is left at zero.
    ppg = (rates["ppg"] or 0.0) * avail
    ppg_horizon = round(ppg * fixture_count, 3)

    # Stale history: the player's most recent Premier League season is not the
    # latest one, usually because he has been in the Championship or abroad.
    # Two things go wrong. The sample is years old and from a different team,
    # and if it predates 2025/26 it has NO defensive-contribution data at all --
    # so dc90 is 0 and the DefCon term silently vanishes, under-projecting
    # defenders in particular. Never trust these without a manual look.
    stale = int(stale_source(src, newest_season))
    new_club = int(joined_new_club(element))
    xp_component_sum = round(
        sum(component_totals[key] for key in (
            "appearance", "goals", "assists", "clean_sheet", "concede_penalty",
            "saves", "defcon", "bonus", "cards", "observed"
        )),
        3,
    )

    return {
        "assumed": assumed,
        "id": element["id"],
        "name": element["web_name"],
        "team": ratings[team_id]["short"],
        "pos": pos,
        "price": element["now_cost"],
        "status": element.get("status", "a"),
        "news": (element.get("news") or "").strip(),
        "selected_by": float(element.get("selected_by_percent") or 0),
        "source": src,
        "no_history": int(no_history),
        "stale": stale,
        "new_club": new_club,
        "avail": round(avail, 2),
        "p_start": round(p_start, 3),
        "xmins": round(xmins, 1),
        "dc90": round(rates["dc90"], 2),
        "per_gw": per_gw,
        "components": component_totals,
        "per_gw_components": per_gw_components,
        "fixtures": fixture_count,
        "xp_horizon": horizon,
        "xp_next": per_gw.get(min(gws), 0.0) if gws else 0.0,
        "xp_appearance": component_totals["appearance"],
        "xp_goals": component_totals["goals"],
        "xp_assists": component_totals["assists"],
        "xp_clean_sheet": component_totals["clean_sheet"],
        "xp_concede_penalty": component_totals["concede_penalty"],
        "xp_saves": component_totals["saves"],
        "xp_defcon": component_totals["defcon"],
        "xp_bonus": component_totals["bonus"],
        "xp_cards": component_totals["cards"],
        "xp_observed": component_totals["observed"],
        "xp_structural": component_totals["structural"],
        "xp_component_sum": xp_component_sum,
        "xp_per_m": round(safe_div(horizon, element["now_cost"] / 10.0), 3),
        "ppg": round(ppg, 3),
        "ppg_horizon": ppg_horizon,
        "xp_edge": round(horizon - ppg_horizon, 3),
    }


def report_only(rows, meta, args) -> int:
    """Render the --top / --disagree / --needs-assumption views.

    Split out so a reporting run can work from cached projections instead of
    recomputing (and overwriting) them at a different horizon.
    """
    if args.top:
        print(f"\n{'name':<16}{'team':<5}{'pos':<5}{'price':>6}{'xmins':>7}"
              f"{'xP/GW':>7}{'xP':>7}{'xP/£m':>7}{'base':>7}{'edge':>7}")
        for row in rows[:args.top]:
            print(f"{row['name'][:15]:<16}{row['team']:<5}{row['pos']:<5}"
                  f"{fmt_price(row['price']):>6}{row['xmins']:>7.0f}"
                  f"{row['xp_next']:>7.2f}{row['xp_horizon']:>7.1f}{row['xp_per_m']:>7.2f}"
                  f"{row['ppg_horizon']:>7.1f}{row['xp_edge']:>+7.1f}")
        print("\n  base = points-per-game baseline over the same fixtures")
        print("  edge = xP - base. Large edges are claims worth checking by hand.")

    if args.needs_assumption:
        blind = [r for r in rows
                 if (r["no_history"] or r["stale"]) and not r.get("assumed")
                 and r["avail"] > 0 and r["status"] == "a"]
        by_team = defaultdict(list)
        for row in blind:
            by_team[row["team"]].append(row)
        worst = sorted(by_team, key=lambda t: -len(by_team[t]))[:args.needs_assumption]
        print("\nPlayers the model cannot see, by club")
        print("  Add an entry to state/minutes-assumptions.json to project one.")
        for team in worst:
            group = sorted(by_team[team], key=lambda r: r["price"], reverse=True)
            total = sum(1 for r in rows if r["team"] == team)
            print(f"\n  {team}: {len(group)} of {total} unmodellable")
            for row in group[:8]:
                print(f"    id={row['id']:<4} {row['name'][:18]:<19}"
                      f"{row['pos']:<5}{fmt_price(row['price']):>6}  {row['source']}")

    if args.disagree:
        ranked = sorted((r for r in rows if not r["no_history"] and r["xmins"] >= 45),
                        key=lambda r: r["xp_edge"])
        print("\nLargest disagreements with the points-per-game baseline")
        print(f"  {'name':<16}{'team':<5}{'pos':<5}{'price':>6}{'xP':>7}{'base':>7}{'edge':>7}")
        print("  -- model most PESSIMISTIC (fading a proven scorer) --")
        for row in ranked[:args.disagree]:
            print(f"  {row['name'][:15]:<16}{row['team']:<5}{row['pos']:<5}"
                  f"{fmt_price(row['price']):>6}{row['xp_horizon']:>7.1f}"
                  f"{row['ppg_horizon']:>7.1f}{row['xp_edge']:>+7.1f}")
        print("  -- model most OPTIMISTIC (backing it against the record) --")
        for row in reversed(ranked[-args.disagree:]):
            print(f"  {row['name'][:15]:<16}{row['team']:<5}{row['pos']:<5}"
                  f"{fmt_price(row['price']):>6}{row['xp_horizon']:>7.1f}"
                  f"{row['ppg_horizon']:>7.1f}{row['xp_edge']:>+7.1f}")
        print("\n  Each of these is a claim worth checking by hand before acting.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, default=None,
                        help="gameweeks to project (default 5, or the cached run)")
    parser.add_argument("--from-gw", type=int, help="start gameweek (default: next)")
    parser.add_argument("--top", type=int, default=0, help="print top N by xp_horizon")
    parser.add_argument("--needs-assumption", type=int, default=0, metavar="N",
                        help="list the N clubs with the most unmodellable players")
    parser.add_argument("--disagree", type=int, default=0, metavar="N",
                        help="show the N players where the model most disagrees "
                             "with the points-per-game baseline")
    args = parser.parse_args()

    try:
        bootstrap = load_bootstrap()
        fixtures = load_fixtures()
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # A reporting-only run must not silently rewrite the file at a different
    # horizon: `project.py --disagree 10` after a `--horizon 6` run used to
    # regenerate at 5 and quietly change what the optimiser would then read.
    reporting_only = (args.top or args.disagree or args.needs_assumption) \
        and args.horizon is None and args.from_gw is None
    cached = json.loads((DATA / "projections.json").read_text()) \
        if reporting_only and (DATA / "projections.json").exists() else None
    if cached:
        rows = cached["players"]
        meta = cached["meta"]
        print(f"reusing cached projections: GW{meta['gameweeks'][0]}-"
              f"{meta['gameweeks'][-1]} ({len(rows)} players, not rewritten)")
        return report_only(rows, meta, args)

    horizon = args.horizon or 5
    start = args.from_gw or (next_event(bootstrap) or {}).get("id")
    if not start:
        print("error: no upcoming gameweek", file=sys.stderr)
        return 1
    gws = list(range(start, start + horizon))

    ratings, source = team_ratings(bootstrap)
    baselines = baseline_goals(ratings)

    # Index by team then gameweek so blanks and doubles fall out naturally.
    by_team: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for fixture in fixtures:
        if fixture.get("event") in gws:
            by_team[fixture["team_h"]][fixture["event"]].append(fixture)
            by_team[fixture["team_a"]][fixture["event"]].append(fixture)

    odds_map = load_odds_map()
    newest = latest_season(bootstrap, load_summary)
    replacement = replacement_rates(bootstrap, load_summary)
    assumptions = load_assumptions()
    horizon_fixtures = {f["id"] for f in fixtures if f.get("event") in gws}
    odds_covered = len(horizon_fixtures & set(odds_map))

    missing_summaries = 0
    rows = []
    for element in bootstrap["elements"]:
        summary = load_summary(element["id"])
        if summary is None:
            missing_summaries += 1
        rows.append(project_player(
            element, summary, ratings, baselines, by_team, gws, odds_map, newest,
            replacement, assumptions))
    rows.sort(key=lambda r: -r["xp_horizon"])

    DATA.mkdir(parents=True, exist_ok=True)
    meta = {
        "gameweeks": gws,
        "strength_source": source,
        "odds_fixtures": odds_covered,
        "total_fixtures": len(horizon_fixtures),
        "missing_summaries": missing_summaries,
        "players": len(rows),
    }
    (DATA / "projections.json").write_text(json.dumps({"meta": meta, "players": rows}, indent=1))

    with (DATA / "projections.csv").open("w", newline="") as handle:
        cols = ["id", "name", "team", "pos", "price", "status", "no_history", "avail",
                "p_start", "xmins", "dc90", "stale", "new_club", "assumed", "fixtures",
                "xp_next", "xp_horizon",
                "xp_appearance", "xp_goals", "xp_assists", "xp_clean_sheet",
                "xp_concede_penalty", "xp_saves", "xp_defcon", "xp_bonus",
                "xp_cards", "xp_observed", "xp_structural", "xp_component_sum",
                "xp_per_m", "ppg", "ppg_horizon", "xp_edge",
                "selected_by", "source", "news"]
        writer = csv.DictWriter(handle, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"projected GW{gws[0]}-{gws[-1]} for {len(rows)} players")
    print(f"  team strength source: {source}")
    if odds_covered:
        print(f"  bookmaker odds cover {odds_covered}/{len(horizon_fixtures)} fixtures "
              "(odds override the strength model where present)")
    else:
        print("  no bookmaker odds -- run scripts/odds.py for sharper fixture difficulty")
    if missing_summaries:
        print(f"  WARNING: {missing_summaries} players lack element-summary history.")
        print("           Run: python scripts/fetch.py --players")
    flagged = sum(r["no_history"] for r in rows)
    print(f"  {flagged} players have too little history to model -- review by hand")
    used = sum(r["assumed"] for r in rows)
    if used:
        print(f"  {used} players projected from ASSUMED minutes "
              f"(state/minutes-assumptions.json) -- replacement-level rates, "
              f"not observed ones")
    movers = [r for r in rows if r["new_club"] and r["xp_horizon"] > 15]
    if movers:
        movers.sort(key=lambda r: -r["xp_horizon"])
        print(f"  {len(movers)} highly-rated players joined a new club since "
              f"{NEW_CLUB_CUTOFF} -- their minutes record is from their OLD club:")
        for row in movers[:6]:
            print(f"    {row['name'][:16]:<17}{row['team']:<5}"
                  f"xP {row['xp_horizon']:>5.1f}  xmins {row['xmins']:>3.0f}")
        if len(movers) > 6:
            print(f"    ... and {len(movers) - 6} more (new_club=1 in the CSV)")
    stale = sum(r["stale"] for r in rows if not r["no_history"])
    if stale:
        print(f"  {stale} more have STALE history (last played the PL before "
              f"{newest}).")
        print("    Those from before 2025/26 have no defensive-contribution data,")
        print("    so their DefCon is scored as zero. Review promoted clubs by hand.")
    print(f"  wrote {DATA / 'projections.csv'}")

    return report_only(rows, meta, args)


if __name__ == "__main__":
    raise SystemExit(main())
