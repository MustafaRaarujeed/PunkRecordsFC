#!/usr/bin/env python3
"""Guardrail checks. Nothing reaches the human until this passes.

    python scripts/validate.py --rules     # our constants still match the live API
    python scripts/validate.py --squad     # state/squad.json is a legal squad
    python scripts/validate.py --all

--rules exists because every projection is built on hardcoded scoring values.
If the Premier League changes a rule mid-season, this fails loudly instead of
letting the model quietly produce wrong numbers for weeks.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from fpl_common import (
    ASSIST_PTS,
    LOG,
    BUDGET,
    CS_PTS,
    DC_PTS,
    GOAL_PTS,
    MAX_FREE_TRANSFERS,
    POS,
    SQUAD_QUOTA,
    SQUAD_SIZE,
    STATE,
    TEAM_LIMIT,
    FetchError,
    fmt_price,
    load_bootstrap,
)


def check_rules(bootstrap: dict) -> list[str]:
    """Assert fpl_common's constants against bootstrap-static game_config."""
    problems: list[str] = []
    scoring = bootstrap["game_config"]["scoring"]
    rules = bootstrap["game_config"]["rules"]

    for pos, expected in GOAL_PTS.items():
        actual = scoring["goals_scored"].get(pos)
        if actual != expected:
            problems.append(f"goals_scored[{pos}]: expected {expected}, API says {actual}")
    for pos, expected in CS_PTS.items():
        actual = scoring["clean_sheets"].get(pos)
        if actual != expected:
            problems.append(f"clean_sheets[{pos}]: expected {expected}, API says {actual}")
    if scoring["assists"] != ASSIST_PTS:
        problems.append(f"assists: expected {ASSIST_PTS}, API says {scoring['assists']}")
    for pos in ("DEF", "MID", "FWD"):
        actual = scoring.get("defensive_contribution", {}).get(pos)
        if actual != DC_PTS:
            problems.append(
                f"defensive_contribution[{pos}]: expected {DC_PTS}, API says {actual}")

    if rules["squad_squadsize"] != SQUAD_SIZE:
        problems.append(f"squad size: expected {SQUAD_SIZE}, API says {rules['squad_squadsize']}")
    if rules["squad_team_limit"] != TEAM_LIMIT:
        problems.append(f"per-club limit: expected {TEAM_LIMIT}, API says {rules['squad_team_limit']}")
    if rules["squad_total_spend"] != BUDGET:
        problems.append(f"budget: expected {BUDGET}, API says {rules['squad_total_spend']}")
    free_cap = rules.get("max_extra_free_transfers", 0) + 1
    if free_cap != MAX_FREE_TRANSFERS:
        problems.append(f"free-transfer cap: expected {MAX_FREE_TRANSFERS}, API says {free_cap}")

    return problems


def check_squad(bootstrap: dict) -> list[str]:
    path = STATE / "squad.json"
    if not path.exists():
        return [f"no squad state at {path} -- run scripts/sync_squad.py"]

    squad = json.loads(path.read_text())
    picks = squad.get("picks", [])
    problems: list[str] = []

    if len(picks) != SQUAD_SIZE:
        problems.append(f"squad has {len(picks)} players, expected {SQUAD_SIZE}")

    ids = [p["id"] for p in picks]
    if len(set(ids)) != len(ids):
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        problems.append(f"duplicate players: {dupes}")

    elements = {e["id"]: e for e in bootstrap["elements"]}
    unknown = [i for i in ids if i not in elements]
    if unknown:
        problems.append(f"player ids not in the game: {unknown}")

    by_pos = Counter(POS[elements[i]["element_type"]] for i in ids if i in elements)
    for pos, quota in SQUAD_QUOTA.items():
        if by_pos.get(pos, 0) != quota:
            problems.append(f"{pos}: have {by_pos.get(pos, 0)}, need {quota}")

    by_team = Counter(elements[i]["team"] for i in ids if i in elements)
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    for team_id, count in by_team.items():
        if count > TEAM_LIMIT:
            problems.append(f"{teams[team_id]}: {count} players, limit is {TEAM_LIMIT}")

    value = sum(p.get("selling_price", 0) for p in picks) + squad.get("bank", 0)
    if value > BUDGET * 1.6:  # generous, but catches a unit mix-up (tenths vs millions)
        problems.append(f"squad value {fmt_price(value)}m looks wrong -- check units")

    free = squad.get("free_transfers")
    if free is not None and not 0 <= free <= MAX_FREE_TRANSFERS:
        problems.append(f"free transfers {free} outside 0-{MAX_FREE_TRANSFERS}")

    return problems


def check_log(bootstrap: dict) -> list[str]:
    """Report gameweeks that have passed without a decision record.

    The numbers are written automatically by optimise.py; the rationale is not,
    because prose depends on someone remembering. A silently missing log is the
    failure mode this catches -- by the time you notice at GW20, the reasoning
    is gone.
    """
    problems: list[str] = []
    finished = [e["id"] for e in bootstrap["events"] if e.get("finished")]
    if not finished:
        print("  no gameweeks finished yet -- nothing to log")
        return problems

    missing_json, missing_prose = [], []
    for gw in finished:
        if not (LOG / f"gw{gw}-decision.json").exists():
            missing_json.append(gw)
        elif not (LOG / f"gw{gw}.md").exists():
            missing_prose.append(gw)

    covered = len(finished) - len(missing_json)
    print(f"  {covered}/{len(finished)} finished gameweeks have a decision record")
    if missing_json:
        problems.append(
            f"no decision record for GW{', GW'.join(map(str, missing_json))} "
            "-- optimise.py was never run for these, or state/log was cleared")
    if missing_prose:
        problems.append(
            f"numbers but no rationale for GW{', GW'.join(map(str, missing_prose))} "
            "-- copy state/log/TEMPLATE.md and fill it in while you still remember")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", action="store_true")
    parser.add_argument("--squad", action="store_true")
    parser.add_argument("--log", action="store_true",
                        help="report gameweeks missing a decision record")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if not (args.rules or args.squad or args.log or args.all):
        parser.print_help()
        return 1

    try:
        bootstrap = load_bootstrap()
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failed = False
    if args.rules or args.all:
        problems = check_rules(bootstrap)
        print("rules: " + ("OK -- constants match the live API" if not problems else "FAILED"))
        for problem in problems:
            print(f"  ! {problem}", file=sys.stderr)
        failed |= bool(problems)

    if args.squad or args.all:
        problems = check_squad(bootstrap)
        print("squad: " + ("OK -- legal squad" if not problems else "FAILED"))
        for problem in problems:
            print(f"  ! {problem}", file=sys.stderr)
        failed |= bool(problems)

    if args.log or args.all:
        print("log:")
        problems = check_log(bootstrap)
        for problem in problems:
            print(f"  ! {problem}", file=sys.stderr)
        # A missing log is a warning, not a failure -- it must never block a
        # deadline-critical run.

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
