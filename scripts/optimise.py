#!/usr/bin/env python3
"""Pick the squad by integer programming rather than by argument.

    python scripts/optimise.py --draft                    # initial 15 from scratch
    python scripts/optimise.py --xi                       # best XI from state/squad.json
    python scripts/optimise.py --transfer --max-transfers 2
    python scripts/optimise.py --draft --lock Haaland --exclude Salah

The optimiser maximises projected points under the real FPL constraints. It is
deliberately the only thing allowed to choose a squad: an LLM asked to "pick a
good team" produces a plausible one, not an optimal one, and cannot show its
working. Judgement enters upstream, by adjusting the xP inputs, and downstream,
by sanity-checking this output -- never by quietly swapping a player in.

Needs pulp:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from fpl_common import (
    BUDGET,
    load_bootstrap,
    LOG,
    DATA,
    MAX_FREE_TRANSFERS,
    SQUAD_QUOTA,
    SQUAD_SIZE,
    STATE,
    TEAM_LIMIT,
    XI_MAX,
    XI_MIN,
    XI_SIZE,
    fmt_price,
)

try:
    import pulp
except ImportError:
    print(
        "error: pulp is not installed.\n"
        "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n"
        "  then run with .venv/bin/python scripts/optimise.py ...",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Bench points are mostly unrealised, but a bench of total non-players is a trap
# come rotation and injury, so they carry a small positive weight.
BENCH_WEIGHT = 0.12
HIT_COST = 4

# A maximiser always finds *some* marginal move, so left alone it will happily
# spend a free transfer for +0.1 xP -- inside the model's own error bars, and it
# burns a transfer that is worth more banked. Below this gain, hold.
MIN_GAIN = 1.5


def load_projections() -> tuple[list[dict], dict]:
    path = DATA / "projections.json"
    if not path.exists():
        print("error: no projections. Run: python scripts/project.py", file=sys.stderr)
        raise SystemExit(1)
    payload = json.loads(path.read_text())
    return payload["players"], payload["meta"]


def load_squad() -> dict:
    path = STATE / "squad.json"
    if not path.exists():
        print(f"error: no squad state at {path}.\n"
              "  Run: python scripts/fetch.py --my-team && python scripts/sync_squad.py",
              file=sys.stderr)
        raise SystemExit(1)
    return json.loads(path.read_text())


def resolve(players: list[dict], names: list[str]) -> set[int]:
    """Map user-supplied names to player ids, refusing ambiguity rather than guessing."""
    ids: set[int] = set()
    for name in names or []:
        matches = [p for p in players if name.lower() in p["name"].lower()]
        if not matches:
            print(f"error: no player matching {name!r}", file=sys.stderr)
            raise SystemExit(1)
        if len(matches) > 1:
            options = ", ".join(f"{m['name']} ({m['team']})" for m in matches[:8])
            print(f"error: {name!r} is ambiguous: {options}", file=sys.stderr)
            raise SystemExit(1)
        ids.add(matches[0]["id"])
    return ids


def build(players, objective_key, budget, current=None, max_transfers=None,
          free_transfers=1, lock=(), exclude=(), bank=0, allow_assumed=False):
    """Shared squad/XI/captain model. `current` switches it into transfer mode."""
    prob = pulp.LpProblem("fpl", pulp.LpMaximize)
    idx = {p["id"]: p for p in players}
    ids = list(idx)

    squad = pulp.LpVariable.dicts("squad", ids, cat="Binary")
    xi = pulp.LpVariable.dicts("xi", ids, cat="Binary")
    cap = pulp.LpVariable.dicts("cap", ids, cat="Binary")

    xp = {i: idx[i][objective_key] for i in ids}

    # --- squad shape ---
    prob += pulp.lpSum(squad.values()) == SQUAD_SIZE
    for pos, quota in SQUAD_QUOTA.items():
        prob += pulp.lpSum(squad[i] for i in ids if idx[i]["pos"] == pos) == quota
    for team in {p["team"] for p in players}:
        prob += pulp.lpSum(squad[i] for i in ids if idx[i]["team"] == team) <= TEAM_LIMIT

    # --- starting XI nested inside the squad ---
    prob += pulp.lpSum(xi.values()) == XI_SIZE
    for pos in SQUAD_QUOTA:
        count = pulp.lpSum(xi[i] for i in ids if idx[i]["pos"] == pos)
        prob += count >= XI_MIN[pos]
        prob += count <= XI_MAX[pos]
    for i in ids:
        prob += xi[i] <= squad[i]
        prob += cap[i] <= xi[i]
    prob += pulp.lpSum(cap.values()) == 1

    # --- money ---
    if current is None:
        prob += pulp.lpSum(idx[i]["price"] * squad[i] for i in ids) <= budget
        transfer_penalty = 0
    else:
        held = {p["id"]: p for p in current["picks"]}
        for i in held:
            if i not in idx:
                print(f"error: squad player id {i} is not in the projections; "
                      "refresh with scripts/fetch.py --core", file=sys.stderr)
                raise SystemExit(1)
        # Sell at the FPL selling price (purchase price plus half the rise),
        # which is what state/squad.json records -- not at now_cost.
        sold = pulp.lpSum(held[i]["selling_price"] * (1 - squad[i]) for i in held)
        bought = pulp.lpSum(idx[i]["price"] * squad[i] for i in ids if i not in held)
        prob += bought <= sold + bank

        n_out = pulp.lpSum(1 - squad[i] for i in held)
        if max_transfers is not None:
            prob += n_out <= max_transfers

        # Hits are only charged beyond the free allowance. paid >= n_out - free
        # with paid >= 0; maximisation drives it down to exactly that.
        paid = pulp.LpVariable("paid_transfers", lowBound=0, cat="Integer")
        prob += paid >= n_out - free_transfers
        transfer_penalty = HIT_COST * paid

    for i in resolve(players, list(lock)):
        prob += squad[i] == 1
    for i in resolve(players, list(exclude)):
        prob += squad[i] == 0

    # Unavailable players are worth zero and would only waste a slot.
    for i in ids:
        if idx[i]["avail"] <= 0:
            prob += squad[i] == 0

    # Players projected from asserted minutes are excluded unless explicitly
    # allowed. Their numbers rest on a human's claim that they start, not on
    # observed history, so they should never enter a squad silently.
    if not allow_assumed:
        for i in ids:
            if idx[i].get("assumed"):
                prob += squad[i] == 0

    prob += (
        pulp.lpSum(xp[i] * xi[i] for i in ids)
        + BENCH_WEIGHT * pulp.lpSum(xp[i] * (squad[i] - xi[i]) for i in ids)
        + pulp.lpSum(xp[i] * cap[i] for i in ids)
        - transfer_penalty
    )

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[status] != "Optimal":
        print(f"error: solver returned {pulp.LpStatus[status]} -- constraints may be "
              "infeasible (check --lock and budget)", file=sys.stderr)
        raise SystemExit(1)

    chosen = [idx[i] for i in ids if squad[i].value() > 0.5]
    starters = {i for i in ids if xi[i].value() > 0.5}
    captain = next(i for i in ids if cap[i].value() > 0.5)
    return chosen, starters, captain


def record_decision(mode, meta, chosen, starters, captain, key, args,
                    current=None, transfer_summary=None) -> None:
    """Write a machine-readable record of what the optimiser decided.

    Written on every run, not on request. The skill also asks the agent to
    write prose alongside, but prose depends on the agent remembering -- and an
    agent that forgets leaves no trace of forgetting. This captures the numbers
    unconditionally so a gameweek can always be audited after the fact, even if
    the narrative is missing.
    """
    gw = meta["gameweeks"][0] if meta.get("gameweeks") else None
    if gw is None:
        return

    held = {p["id"] for p in current["picks"]} if current else set()
    record = {
        "gameweek": gw,
        "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": mode,
        "objective": key,
        "horizon": meta.get("gameweeks"),
        "strength_source": meta.get("strength_source"),
        "odds_fixtures": meta.get("odds_fixtures"),
        "allow_assumed": bool(args.allow_assumed),
        "squad": [
            {
                "id": p["id"], "name": p["name"], "team": p["team"], "pos": p["pos"],
                "price": p["price"], "xp": p[key],
                "ppg_horizon": p.get("ppg_horizon"), "xp_edge": p.get("xp_edge"),
                "starter": p["id"] in starters,
                "captain": p["id"] == captain,
                "incoming": bool(current) and p["id"] not in held,
                "assumed": p.get("assumed", 0),
                "no_history": p.get("no_history", 0),
                "stale": p.get("stale", 0),
                "news": p.get("news", ""),
            }
            for p in chosen
        ],
        "squad_cost": sum(p["price"] for p in chosen),
    }
    if current:
        record["out"] = [
            {"id": p["id"], "name": p.get("name")}
            for p in current["picks"] if p["id"] not in {c["id"] for c in chosen}
        ]
        # Bank is deliberately omitted: state/squad.json is gitignored for
        # holding it, and these records are meant to be committable as the
        # season's audit trail. hits_paid already records whether a move cost
        # points, which is the part that matters when auditing the decision.
    if transfer_summary:
        record.update(transfer_summary)

    LOG.mkdir(parents=True, exist_ok=True)
    path = LOG / f"gw{gw}-decision.json"
    path.write_text(json.dumps(record, indent=1))
    print(f"\n  decision recorded -> {path.relative_to(LOG.parent.parent)}")
    if not (LOG / f"gw{gw}.md").exists():
        print(f"  NOTE: no written rationale yet at state/log/gw{gw}.md")
        print("        Copy state/log/TEMPLATE.md and fill it in -- the numbers are")
        print("        captured above, but not why you chose them.")


def assert_legal(chosen, starters, captain, budget) -> None:
    """Re-check the solver's own output before a human ever sees it.

    The ILP constraints should make this impossible, which is exactly why it is
    worth checking: a bug in how the constraints are built would otherwise
    surface as an illegal squad at a deadline. validate.py --squad cannot cover
    the draft, because state/squad.json does not exist yet.
    """
    from collections import Counter
    problems = []
    if len(chosen) != SQUAD_SIZE:
        problems.append(f"{len(chosen)} players, expected {SQUAD_SIZE}")
    by_pos = Counter(p["pos"] for p in chosen)
    for pos, quota in SQUAD_QUOTA.items():
        if by_pos.get(pos, 0) != quota:
            problems.append(f"{pos}: {by_pos.get(pos, 0)}, need {quota}")
    for team, n in Counter(p["team"] for p in chosen).items():
        if n > TEAM_LIMIT:
            problems.append(f"{team}: {n} players, limit {TEAM_LIMIT}")
    cost = sum(p["price"] for p in chosen)
    if cost > budget:
        problems.append(f"cost {fmt_price(cost)}m exceeds {fmt_price(budget)}m")
    if len(starters) != XI_SIZE:
        problems.append(f"{len(starters)} starters, expected {XI_SIZE}")
    xi_pos = Counter(p["pos"] for p in chosen if p["id"] in starters)
    for pos in SQUAD_QUOTA:
        n = xi_pos.get(pos, 0)
        if not XI_MIN[pos] <= n <= XI_MAX[pos]:
            problems.append(f"XI {pos}: {n}, must be {XI_MIN[pos]}-{XI_MAX[pos]}")
    if captain not in starters:
        problems.append("captain is not in the starting XI")

    if problems:
        print("error: the optimiser produced an ILLEGAL squad -- not showing it.",
              file=sys.stderr)
        for problem in problems:
            print(f"  ! {problem}", file=sys.stderr)
        raise SystemExit(1)


def xi_total(players, starters, captain, key) -> float:
    """Projected XI points, counting the captain twice."""
    idx = {p["id"]: p for p in players}
    total = sum(idx[i][key] for i in starters if i in idx)
    return total + idx[captain][key] if captain in idx else total


def report(chosen, starters, captain, objective_key, current=None):
    order = {"GKP": 0, "DEF": 1, "MID": 2, "FWD": 3}
    chosen.sort(key=lambda p: (order[p["pos"]], -p[objective_key]))
    held = {p["id"] for p in current["picks"]} if current else set()

    print(f"\n{'':<3}{'name':<16}{'team':<5}{'pos':<5}{'price':>6}{'xP':>7}{'own%':>7}  flags")
    total_price = total_xp = 0
    for player in chosen:
        marks = []
        if player["id"] == captain:
            marks.append("(C)")
        if current and player["id"] not in held:
            marks.append("IN")
        if player.get("assumed"):
            marks.append("ASSUMED-MINUTES")
        elif player["no_history"]:
            marks.append("no-history")
        if player["news"]:
            marks.append(player["news"][:38])
        role = "XI " if player["id"] in starters else "sub"
        print(f"{role:<3}{player['name'][:15]:<16}{player['team']:<5}{player['pos']:<5}"
              f"{fmt_price(player['price']):>6}{player[objective_key]:>7.2f}"
              f"{player['selected_by']:>7.1f}  {' '.join(marks)}")
        total_price += player["price"]
        if player["id"] in starters:
            total_xp += player[objective_key]

    cap_player = next(p for p in chosen if p["id"] == captain)
    print(f"\n  squad cost   {fmt_price(total_price)}m of {fmt_price(BUDGET)}m"
          f"  (bank {fmt_price(BUDGET - total_price)}m)")
    print(f"  XI projected {total_xp + cap_player[objective_key]:.1f} pts "
          f"(captain {cap_player['name']} doubled)")
    if current:
        out = [p for p in current["picks"] if p["id"] not in {c["id"] for c in chosen}]
        for player in out:
            print(f"  OUT  {player.get('name', player['id'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--draft", action="store_true", help="build 15 from scratch")
    mode.add_argument("--xi", action="store_true", help="best XI from current squad")
    mode.add_argument("--transfer", action="store_true", help="propose transfers")
    parser.add_argument("--horizon", action="store_true",
                        help="optimise the multi-week horizon rather than the next GW")
    parser.add_argument("--max-transfers", type=int, default=2)
    parser.add_argument("--allow-assumed", action="store_true",
                        help="let the optimiser pick players projected from "
                             "asserted minutes (state/minutes-assumptions.json)")
    parser.add_argument("--min-gain", type=float, default=MIN_GAIN,
                        help="net xP gain required to recommend transferring")
    parser.add_argument("--budget", type=int, default=BUDGET, help="tenths of a million")
    parser.add_argument("--reserve", type=int, default=0, metavar="TENTHS",
                        help="hold this much back (e.g. 5 = 0.5m) to absorb "
                             "overnight price moves before the deadline")
    parser.add_argument("--lock", action="append", default=[], help="force a player in")
    parser.add_argument("--exclude", action="append", default=[], help="force a player out")
    args = parser.parse_args()

    players, meta = load_projections()
    if args.reserve:
        args.budget -= args.reserve
        print(f"  reserving {fmt_price(args.reserve)}m -- optimising against "
              f"{fmt_price(args.budget)}m")
    print(f"projections: GW{meta['gameweeks'][0]}-{meta['gameweeks'][-1]}  "
          f"strength source: {meta['strength_source']}")
    if "preseason" in meta["strength_source"]:
        print("  NOTE: preseason fallback in use -- fixture difficulty is low confidence")

    # Draft looks at the whole horizon; a one-week XI call looks at the next GW.
    key = "xp_horizon" if (args.draft or args.horizon) else "xp_next"

    if args.draft:
        chosen, starters, captain = build(
            players, key, args.budget, lock=args.lock, exclude=args.exclude,
            allow_assumed=args.allow_assumed)
        assert_legal(chosen, starters, captain, args.budget)
        report(chosen, starters, captain, key)
        record_decision("draft", meta, chosen, starters, captain, key, args)
        return 0

    squad = load_squad()
    if args.xi:
        held = {p["id"] for p in squad["picks"]}
        subset = [p for p in players if p["id"] in held]
        if len(subset) != SQUAD_SIZE:
            print(f"error: squad state has {len(subset)} of {SQUAD_SIZE} players",
                  file=sys.stderr)
            return 1
        chosen, starters, captain = build(
            subset, key, args.budget, lock=args.lock, exclude=args.exclude,
            allow_assumed=True)  # already in the squad; do not silently drop
        assert_legal(chosen, starters, captain, args.budget)
        report(chosen, starters, captain, key)
        record_decision("xi", meta, chosen, starters, captain, key, args,
                        current=squad)
        return 0

    # Before the first deadline there are no transfers: squad changes are
    # unlimited and free, and FPL reports free_transfers as null. Running
    # transfer mode here quietly does two wrong things -- it treats an
    # incremental swap as the only option, and it anchors on whatever is
    # already in the squad, which for a new account is FPL's auto-pick rather
    # than a considered team. Draft mode is the right tool.
    bootstrap = load_bootstrap()
    if not any(e.get("finished") for e in bootstrap["events"]):
        print("\nerror: no gameweek has finished yet -- transfers do not apply.",
              file=sys.stderr)
        print("  Squad changes are unlimited and free before the first deadline,"
              " and a new\n  account's squad is FPL's auto-pick, not a considered"
              " starting point.\n  Use: optimise.py --draft", file=sys.stderr)
        return 1

    free = min(squad.get("free_transfers", 1), MAX_FREE_TRANSFERS)
    print(f"  bank {fmt_price(squad.get('bank', 0))}m, {free} free transfer(s)")

    common = dict(current=squad, free_transfers=free, bank=squad.get("bank", 0),
                  lock=args.lock, exclude=args.exclude,
                  allow_assumed=args.allow_assumed)
    # Baseline: what the squad scores if we do nothing. Every proposal is judged
    # against holding, not against zero.
    _, hold_xi, hold_cap = build(players, key, args.budget, max_transfers=0, **common)
    hold_xp = xi_total(players, hold_xi, hold_cap, key)

    chosen, starters, captain = build(
        players, key, args.budget, max_transfers=args.max_transfers, **common)
    move_xp = xi_total(players, starters, captain, key)

    held = {p["id"] for p in squad["picks"]}
    n_moves = len([p for p in chosen if p["id"] not in held])
    paid = max(0, n_moves - free)
    gain = move_xp - hold_xp - paid * HIT_COST

    assert_legal(chosen, starters, captain, args.budget)
    report(chosen, starters, captain, key, current=squad)
    print(f"\n  hold          {hold_xp:.2f} xP")
    print(f"  {n_moves} transfer(s)  {move_xp:.2f} xP"
          + (f"  (-{paid * HIT_COST} hit)" if paid else ""))
    print(f"  net gain      {gain:+.2f} xP  (threshold {args.min_gain:.2f})")
    if gain < args.min_gain:
        print("\n  RECOMMENDATION: hold. The gain is inside the model's error bars,")
        print("  and a banked transfer is worth more than a marginal one.")
    else:
        print("\n  RECOMMENDATION: make the transfer(s).")

    record_decision("transfer", meta, chosen, starters, captain, key, args,
                    current=squad,
                    transfer_summary={
                        "hold_xp": round(hold_xp, 3),
                        "move_xp": round(move_xp, 3),
                        "transfers": n_moves,
                        "hits_paid": paid,
                        "net_gain": round(gain, 3),
                        "min_gain": args.min_gain,
                        "recommendation": "move" if gain >= args.min_gain else "hold",
                    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
