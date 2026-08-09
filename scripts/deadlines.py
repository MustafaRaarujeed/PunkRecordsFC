#!/usr/bin/env python3
"""Show FPL deadlines in Sydney local time, with the sessions to act in.

    python scripts/deadlines.py            # next deadline + countdown
    python scripts/deadlines.py --season    # all 38 gameweeks
    python scripts/deadlines.py --gw 12     # one gameweek

FPL publishes deadlines in UTC. In Sydney most of them land just after midnight
on Sunday, and a handful at 03:30 Saturday or 05:30 Thursday, so this reports
the last civil evening to finalise rather than a naive "two hours before".
"""

from __future__ import annotations

import argparse
import sys

from fpl_common import (
    LOCAL_ZONE_LABEL,
    FetchError,
    deadline_brief,
    load_bootstrap,
    next_event,
)


def render(event: dict, verbose: bool) -> None:
    brief = deadline_brief(event)
    flag = "  <- overnight deadline" if brief["overnight"] else ""
    if not verbose:
        print(f"GW{brief['gw']:<3} {brief['deadline_syd']:<22} lock: {brief['lock_syd']}{flag}")
        return

    print(f"GW{brief['gw']}")
    print(f"  deadline (UTC)    {brief['deadline_utc']:%a %d %b %Y %H:%M} UTC")
    print(f"  deadline (local)  {brief['deadline_syd']}{flag}   [{LOCAL_ZONE_LABEL}]")
    print(f"  plan session      {brief['plan_syd']}")
    print(f"  lock session      {brief['lock_syd']}")
    if brief["hours_to_deadline"] > 0:
        print(f"  time remaining    {brief['hours_to_deadline']:.1f}h to deadline, "
              f"{brief['hours_to_lock']:.1f}h to lock")
    else:
        print("  time remaining    deadline passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", action="store_true", help="list all 38 gameweeks")
    parser.add_argument("--gw", type=int, help="show one gameweek")
    args = parser.parse_args()

    try:
        bootstrap = load_bootstrap()
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    events = bootstrap["events"]

    if args.season:
        print(f"{'GW':<5} {'deadline (' + LOCAL_ZONE_LABEL + ')':<26} finalise by")
        for event in events:
            render(event, verbose=False)
        return 0

    if args.gw:
        match = next((e for e in events if e["id"] == args.gw), None)
        if not match:
            print(f"error: no gameweek {args.gw}", file=sys.stderr)
            return 1
        render(match, verbose=True)
        return 0

    event = next_event(bootstrap)
    if not event:
        print("season complete -- no upcoming deadline")
        return 0
    render(event, verbose=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
