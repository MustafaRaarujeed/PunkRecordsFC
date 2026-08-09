#!/usr/bin/env python3
"""Write state/squad.json from the authenticated my-team payload.

    python scripts/fetch.py --my-team && python scripts/sync_squad.py
    python scripts/sync_squad.py --from-file <path>   # any location
    python scripts/sync_squad.py --from-draft 123,456,...   # seed before GW1

With FPL_ACCESS_TOKEN set, `fetch.py --my-team` writes data/my-team.json and
this reads it -- no arguments needed.

Without credentials: open

    https://fantasy.premierleague.com/api/my-team/<ENTRY_ID>/

in a logged-in browser and save it to data/my-team.json, which is the same path
and is gitignored. Then run this with no arguments too. --from-file exists only
for a file saved somewhere else.

state/squad.json is the single source of truth for what we own, what it can be
sold for, and how many free transfers are banked. It is never copied anywhere:
two copies of this file means the agent reads one, writes the other, and your
squad silently drifts from reality.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fpl_common import (
    POS,
    SQUAD_SIZE,
    STATE,
    FetchError,
    cache_path,
    fmt_price,
    load_bootstrap,
    next_event,
    read_cache,
)


def write_state(payload: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / "squad.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"wrote {path}")
    print(f"  {len(payload['picks'])} players, bank {fmt_price(payload['bank'])}m, "
          f"{payload['free_transfers']} free transfer(s)")


def from_my_team(bootstrap: dict, path=None) -> dict:
    if path is not None:
        source = Path(path).expanduser()
        if not source.exists():
            raise FetchError(f"no such file: {source}")
        try:
            my_team = json.loads(source.read_text())
        except json.JSONDecodeError as exc:
            raise FetchError(f"{source} is not valid JSON: {exc}") from exc
        if "picks" not in my_team:
            raise FetchError(
                f"{source} has no 'picks' key -- this is not a my-team payload. "
                "Open https://fantasy.premierleague.com/api/my-team/<ENTRY_ID>/ "
                "while logged in and save that response."
            )
    else:
        my_team = read_cache(cache_path("my-team"))
        if my_team is None:
            raise FetchError(
                f"No my-team data at {cache_path('my-team')}.\n"
                "  Either: set FPL_ACCESS_TOKEN in .env and run "
                "scripts/fetch.py --my-team\n"
                "  Or:     open https://fantasy.premierleague.com/api/my-team/"
                "<ENTRY_ID>/ in a logged-in\n"
                "          browser and save the response to that path."
            )

    elements = {e["id"]: e for e in bootstrap["elements"]}
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    transfers = my_team.get("transfers", {})
    event = next_event(bootstrap)

    picks = []
    for pick in my_team.get("picks", []):
        element = elements.get(pick["element"])
        if element is None:
            raise FetchError(f"my-team references unknown player {pick['element']}")
        picks.append({
            "id": element["id"],
            "name": element["web_name"],
            "team": teams[element["team"]],
            "pos": POS[element["element_type"]],
            "purchase_price": pick.get("purchase_price", element["now_cost"]),
            "selling_price": pick.get("selling_price", element["now_cost"]),
            "now_cost": element["now_cost"],
        })

    return {
        "source": "my-team",
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gameweek": event["id"] if event else None,
        "bank": transfers.get("bank", 0),
        "value": transfers.get("value", 0),
        "free_transfers": transfers.get("limit") or 1,
        "chips_used": [c["name"] for c in my_team.get("chips", []) if c.get("status_for_entry") == "played"],
        "picks": picks,
    }


def from_draft(bootstrap: dict, ids: list[int]) -> dict:
    """Seed state before the account exists, from an optimiser draft.

    Purchase price is now_cost since nothing has been bought yet.
    """
    elements = {e["id"]: e for e in bootstrap["elements"]}
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    event = next_event(bootstrap)

    picks = []
    for pid in ids:
        element = elements.get(pid)
        if element is None:
            raise FetchError(f"unknown player id {pid}")
        picks.append({
            "id": element["id"],
            "name": element["web_name"],
            "team": teams[element["team"]],
            "pos": POS[element["element_type"]],
            "purchase_price": element["now_cost"],
            "selling_price": element["now_cost"],
            "now_cost": element["now_cost"],
        })

    spent = sum(p["purchase_price"] for p in picks)
    return {
        "source": "draft",
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gameweek": event["id"] if event else None,
        "bank": 1000 - spent,
        "value": spent,
        "free_transfers": 1,
        "chips_used": [],
        "picks": picks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-draft", help="comma-separated player ids to seed with")
    parser.add_argument("--from-file", help="my-team JSON saved from a logged-in browser")
    args = parser.parse_args()

    try:
        bootstrap = load_bootstrap()
        if args.from_draft:
            ids = [int(x) for x in args.from_draft.split(",") if x.strip()]
            if len(ids) != SQUAD_SIZE:
                print(f"error: got {len(ids)} ids, need {SQUAD_SIZE}", file=sys.stderr)
                return 1
            payload = from_draft(bootstrap, ids)
        else:
            payload = from_my_team(bootstrap, args.from_file)
    except (FetchError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_state(payload)
    print("  now run: python scripts/validate.py --squad")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
