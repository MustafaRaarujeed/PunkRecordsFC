#!/usr/bin/env python3
"""Derive per-fixture expected goals from bookmaker odds.

    python scripts/odds.py            # fetch and write data/odds.json
    python scripts/odds.py --show     # print what we have, no API call

Bookmakers price matches better than any public model, and in preseason they
are the only good signal at all: the API's strength_attack_* and
strength_defence_* fields are zero until matches are played.

Method, per fixture:
  1. De-vig the 1X2 prices into true win/draw/loss probabilities.
  2. Invert the over/under line under a Poisson total to recover expected total
     goals T.
  3. Solve for the supremacy S that reproduces the home win probability, with
     home and away goals as independent Poissons.
  4. Expected goals are then (T + S) / 2 and (T - S) / 2.

Costs one request per call. The free tier allows 500/month, so a weekly pull is
comfortable. Results are cached; --show never hits the network.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
from datetime import datetime, timezone

from fpl_common import (
    DATA,
    LEAGUE_AVG_GOALS,
    FetchError,
    cache_path,
    http_get,
    load_bootstrap,
    load_fixtures,
    load_env,
    parse_utc,
)

ODDS_URL = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds/"
MAX_GOALS = 12  # Poisson tail beyond this is negligible

# The Odds API uses full club names; FPL uses short ones. Only the genuinely
# ambiguous cases need an alias -- the rest fall out of token matching.
ALIASES = {
    "manchester city": "MCI",
    "manchester united": "MUN",
    "tottenham hotspur": "TOT",
    "nottingham forest": "NFO",
    "brighton and hove albion": "BHA",
    "brighton hove albion": "BHA",
    "newcastle united": "NEW",
    "west ham united": "WHU",
    "leeds united": "LEE",
    "afc bournemouth": "BOU",
    "wolverhampton wanderers": "WOL",
    "sunderland afc": "SUN",
}


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def poisson_cdf(k: int, lam: float) -> float:
    return sum(poisson_pmf(i, lam) for i in range(k + 1))


def devig(prices: dict[str, float]) -> dict[str, float]:
    """Decimal odds -> probabilities, with the bookmaker margin divided out."""
    raw = {k: 1.0 / v for k, v in prices.items() if v and v > 1.0}
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in raw.items()}


def solve_total(line: float, p_over: float) -> float:
    """Expected total goals implied by an over/under line, by bisection.

    Under Poisson(T), P(total > line) = 1 - CDF(floor(line)).
    """
    floor_line = math.floor(line)
    lo, hi = 0.3, 7.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if 1.0 - poisson_cdf(floor_line, mid) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def home_win_prob(xg_h: float, xg_a: float) -> float:
    home = [poisson_pmf(i, xg_h) for i in range(MAX_GOALS)]
    away = [poisson_pmf(i, xg_a) for i in range(MAX_GOALS)]
    return sum(home[h] * sum(away[:h]) for h in range(1, MAX_GOALS))


def solve_supremacy(total: float, p_home: float) -> float:
    """Goal supremacy reproducing the home win probability, by bisection."""
    lo, hi = -total + 0.01, total - 0.01
    for _ in range(60):
        mid = (lo + hi) / 2
        if home_win_prob((total + mid) / 2, (total - mid) / 2) < p_home:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def build_team_index(bootstrap: dict) -> dict[str, int]:
    """Map every plausible spelling of a club to its FPL team id."""
    index: dict[str, int] = {}
    by_short = {t["short_name"]: t["id"] for t in bootstrap["teams"]}
    for team in bootstrap["teams"]:
        index[team["name"].lower()] = team["id"]
        index[team["short_name"].lower()] = team["id"]
    for alias, short in ALIASES.items():
        if short in by_short:
            index[alias] = by_short[short]
    return index


def match_team(name: str, index: dict[str, int], bootstrap: dict) -> int | None:
    """Resolve a bookmaker's club name to an FPL team id, or None."""
    key = name.strip().lower()
    if key in index:
        return index[key]

    # Strip common suffixes, then require a distinctive token to overlap.
    stripped = key
    for suffix in (" fc", " afc", " united", " city", " town", " hotspur", " wanderers"):
        stripped = stripped.replace(suffix, "")
    stripped = stripped.strip()
    if stripped in index:
        return index[stripped]

    hits = [tid for spelling, tid in index.items() if stripped and stripped in spelling]
    if len(set(hits)) == 1:
        return hits[0]
    return None


def fetch_odds(api_key: str) -> list:
    query = urllib.parse.urlencode({
        "apiKey": api_key,
        "regions": "uk",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
    })
    return http_get(f"{ODDS_URL}?{query}")


def extract(event: dict) -> tuple[float, float] | None:
    """Expected (home, away) goals for one bookmaker event."""
    h2h_prices: dict[str, list[float]] = {}
    total_points: list[tuple[float, float]] = []

    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            if market["key"] == "h2h":
                for outcome in market["outcomes"]:
                    h2h_prices.setdefault(outcome["name"], []).append(outcome["price"])
            elif market["key"] == "totals":
                over = next((o for o in market["outcomes"] if o["name"] == "Over"), None)
                under = next((o for o in market["outcomes"] if o["name"] == "Under"), None)
                if over and under and over.get("point") is not None:
                    probs = devig({"over": over["price"], "under": under["price"]})
                    if probs:
                        total_points.append((over["point"], probs["over"]))

    if len(h2h_prices) < 3:
        return None

    # Consensus across books: the median price is more robust than any one book.
    consensus = {name: sorted(p)[len(p) // 2] for name, p in h2h_prices.items()}
    probs = devig(consensus)
    home, away = event["home_team"], event["away_team"]
    if home not in probs or away not in probs:
        return None

    if total_points:
        line, p_over = min(total_points, key=lambda lp: abs(lp[1] - 0.5))
        total = solve_total(line, p_over)
    else:
        total = LEAGUE_AVG_GOALS * 2

    supremacy = solve_supremacy(total, probs[home])
    return (total + supremacy) / 2, (total - supremacy) / 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", action="store_true", help="print cache, no API call")
    args = parser.parse_args()

    try:
        bootstrap = load_bootstrap()
        fixtures = load_fixtures()
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    path = cache_path("odds")
    if args.show:
        cached = json.loads(path.read_text()) if path.exists() else None
        if not cached:
            print("no odds cached -- run without --show")
            return 1
        teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
        print(f"generated {cached['generated']}  ({cached['coverage']} fixtures)")
        for row in cached["fixtures"]:
            print(f"  GW{row['event']:<3} {teams[row['team_h']]:>4} {row['xg_h']:.2f}"
                  f" - {row['xg_a']:.2f} {teams[row['team_a']]:<4}")
        return 0

    api_key = load_env().get("ODDS_API_KEY", "").strip()
    if not api_key:
        print("error: ODDS_API_KEY not set in .env -- see .env.example", file=sys.stderr)
        return 1

    try:
        events = fetch_odds(api_key)
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    index = build_team_index(bootstrap)
    # Match on team pair; bookmakers and FPL disagree on exact kickoff times.
    upcoming = {(f["team_h"], f["team_a"]): f for f in fixtures if not f.get("finished")}

    rows, unmatched = [], []
    for event in events:
        home = match_team(event["home_team"], index, bootstrap)
        away = match_team(event["away_team"], index, bootstrap)
        if home is None or away is None:
            unmatched.append(f"{event['home_team']} v {event['away_team']}")
            continue
        fixture = upcoming.get((home, away))
        if fixture is None:
            continue
        goals = extract(event)
        if goals is None:
            continue
        rows.append({
            "fixture": fixture["id"],
            "event": fixture.get("event"),
            "team_h": home,
            "team_a": away,
            "xg_h": round(goals[0], 3),
            "xg_a": round(goals[1], 3),
            "kickoff": event.get("commence_time"),
        })

    DATA.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverage": len(rows),
        "fixtures": rows,
    }
    path.write_text(json.dumps(payload, indent=1))

    print(f"wrote {path}: {len(rows)} fixtures priced")
    if unmatched:
        print(f"  {len(unmatched)} unmatched club names -- add to ALIASES in odds.py:",
              file=sys.stderr)
        for name in unmatched:
            print(f"    {name}", file=sys.stderr)
    print("  now rerun: python scripts/project.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
