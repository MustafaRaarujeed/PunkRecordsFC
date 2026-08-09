#!/usr/bin/env python3
"""Pull FPL data into data/ as a local cache.

    python scripts/fetch.py --core            # bootstrap-static + fixtures
    python scripts/fetch.py --players         # element-summary for every player
    python scripts/fetch.py --my-team         # authenticated squad/bank/FT state
    python scripts/fetch.py --all             # all of the above
    python scripts/fetch.py --core --force    # ignore cache age

Everything is cached to disk and only refetched when stale, because --players
is 570+ requests and we are a guest on someone else's API.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from fpl_common import (
    BASE_URL,
    token_expiry,
    DATA,
    SUMMARIES,
    FetchError,
    cache_path,
    http_get,
    load_env,
    next_event,
    read_cache,
    write_cache,
)

CORE_MAX_AGE_H = 6.0
SUMMARY_MAX_AGE_H = 24.0
REQUEST_DELAY_S = 0.35  # be a polite client on the 570-request sweep


def fetch_core(force: bool) -> dict:
    # 0, not None: read_cache treats None as 'never expires', so passing
    # None here would guarantee a cache hit -- the opposite of --force.
    max_age = 0 if force else CORE_MAX_AGE_H

    bootstrap = read_cache(cache_path("bootstrap-static"), max_age)
    if bootstrap is None:
        print("fetching bootstrap-static ...")
        bootstrap = http_get(f"{BASE_URL}/bootstrap-static/")
        write_cache(cache_path("bootstrap-static"), bootstrap)
    else:
        print("bootstrap-static: cache hit")

    fixtures = read_cache(cache_path("fixtures"), max_age)
    if fixtures is None:
        print("fetching fixtures ...")
        fixtures = http_get(f"{BASE_URL}/fixtures/")
        write_cache(cache_path("fixtures"), fixtures)
    else:
        print("fixtures: cache hit")

    event = next_event(bootstrap)
    if event:
        print(f"next deadline: GW{event['id']} {event['deadline_time']}")
    print(f"players: {len(bootstrap['elements'])}  teams: {len(bootstrap['teams'])}")
    return bootstrap


def fetch_players(bootstrap: dict, force: bool) -> None:
    """element-summary for every player: history_past is the preseason model input."""
    max_age = 0 if force else SUMMARY_MAX_AGE_H  # see fetch_core: 0, not None
    elements = bootstrap["elements"]
    SUMMARIES.mkdir(parents=True, exist_ok=True)

    fetched = cached = failed = 0
    for i, element in enumerate(elements, 1):
        pid = element["id"]
        path = SUMMARIES / f"{pid}.json"
        if read_cache(path, max_age) is not None:
            cached += 1
            continue
        try:
            write_cache(path, http_get(f"{BASE_URL}/element-summary/{pid}/"))
            fetched += 1
        except FetchError as exc:
            print(f"  ! {element['web_name']} ({pid}): {exc}", file=sys.stderr)
            failed += 1
        time.sleep(REQUEST_DELAY_S)
        if i % 50 == 0:
            print(f"  {i}/{len(elements)} ...")

    print(f"element-summary: {fetched} fetched, {cached} cached, {failed} failed")
    if failed:
        print("  rerun --players to retry the failures", file=sys.stderr)


def fetch_my_team() -> None:
    """Authenticated squad state: bank, purchase prices, free transfers, chips.

    The only endpoint needing credentials. FPL uses bearer auth: cookies return
    403 however complete the jar, while `Authorization: Bearer <access_token>`
    works. Tokens last ~8 hours, so expiry is checked locally first -- an
    expired token otherwise surfaces as an indistinguishable 403.
    """
    env = load_env()
    entry_id = env.get("FPL_ENTRY_ID", "").strip()
    token = env.get("FPL_ACCESS_TOKEN", "").strip()

    if not entry_id:
        raise FetchError("FPL_ENTRY_ID not set in .env -- see .env.example")
    if not token:
        raise FetchError(
            "FPL_ACCESS_TOKEN not set in .env. Log in to fantasy.premierleague.com,"
            " then DevTools -> Application -> Cookies -> copy `access_token`."
            " It lasts about 8 hours, so grab it at the start of a session."
            "\n  Or store no credentials at all: save the my-team JSON from a"
            " logged-in browser to data/my-team.json and run scripts/sync_squad.py")

    if token:
        expiry = token_expiry(token)
        if expiry is not None:
            remaining = (expiry - time.time()) / 3600
            if remaining <= 0:
                raise FetchError(
                    f"FPL_ACCESS_TOKEN expired "
                    f"{datetime.fromtimestamp(expiry):%H:%M on %a %d %b}. "
                    "Grab a fresh one: log in, DevTools -> Application -> "
                    "Cookies -> access_token.")
            print(f"  token valid for another {remaining:.1f}h")

    print(f"fetching my-team for entry {entry_id} ...")
    payload = http_get(f"{BASE_URL}/my-team/{entry_id}/", bearer=token)
    write_cache(cache_path("my-team"), payload)

    picks = payload.get("picks", [])
    transfers = payload.get("transfers", {})
    print(f"  squad: {len(picks)} players")
    print(f"  bank: {transfers.get('bank', 0) / 10:.1f}m  "
          f"value: {transfers.get('value', 0) / 10:.1f}m  "
          f"free transfers: {transfers.get('limit')}")
    print("  now run: python scripts/sync_squad.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", action="store_true", help="bootstrap-static + fixtures")
    parser.add_argument("--players", action="store_true", help="element-summary sweep")
    parser.add_argument("--my-team", action="store_true", help="authenticated squad state")
    parser.add_argument("--all", action="store_true", help="core + players + my-team")
    parser.add_argument("--force", action="store_true", help="ignore cache age")
    args = parser.parse_args()

    if not (args.core or args.players or args.my_team or args.all):
        parser.print_help()
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    want_core = args.core or args.all or args.players
    want_players = args.players or args.all
    want_my_team = args.my_team or args.all

    try:
        bootstrap = fetch_core(args.force) if want_core else None
        if want_players:
            fetch_players(bootstrap, args.force)
        if want_my_team:
            # Non-fatal under --all so a stale cookie never blocks a data refresh.
            try:
                fetch_my_team()
            except FetchError as exc:
                if not args.all:
                    raise
                print(f"my-team skipped: {exc}", file=sys.stderr)
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
