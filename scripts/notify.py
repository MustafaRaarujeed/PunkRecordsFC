#!/usr/bin/env python3
"""Send a deadline reminder to Telegram. Built to run from GitHub Actions.

    python3 scripts/notify.py --chat-id     # find your TELEGRAM_CHAT_ID
    python3 scripts/notify.py --dry-run     # print, send nothing
    python3 scripts/notify.py --force       # send now, ignoring the window
    python3 scripts/notify.py               # send if inside an alert window

Exists because the system is worthless if the deadline is missed, and from
Sydney 26 of 38 deadlines land overnight -- so "I'll remember" does not work.

Needs no FPL credentials: deadlines are public. The only secrets are the
Telegram bot token and chat id, which come from the environment (GitHub
Secrets) or, running locally, from .env.

Alert windows, measured against the LOCK session -- the last civil Sydney
evening to act -- not the raw deadline:

    <= 6h    act tonight
    <= 30h   heads-up, plan tomorrow
    else     silent
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from fpl_common import (
    BASE_URL,
    UA,
    FetchError,
    deadline_brief,
    http_get,
    load_env,
    next_event,
    redact,
)

URGENT_HOURS = 6
HEADSUP_HOURS = 30
TELEGRAM_API = "https://api.telegram.org"


def setting(name: str) -> str:
    """Environment first (GitHub Secrets), then .env for local runs."""
    return (os.environ.get(name) or load_env().get(name, "")).strip()


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(url, data=payload, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200] if exc.fp else ""
        # Never echo the URL: the bot token is in the path.
        raise FetchError(f"Telegram returned {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FetchError(f"Telegram unreachable: {exc}") from exc
    if not body.get("ok"):
        raise FetchError(f"Telegram rejected the message: {body.get('description')}")


def show_chat_ids(token: str) -> int:
    """Print the chat ids that have messaged this bot.

    Telegram has no lookup for "my chat id" -- it only appears once the bot has
    RECEIVED a message, which is the step everyone misses. This reads
    getUpdates and extracts the ids so nobody has to read raw JSON.
    """
    # Reported separately from getUpdates: a bot that already has a webhook
    # cannot use getUpdates at all, and the raw 409 does not make that obvious.
    try:
        hook = http_get(f"{TELEGRAM_API}/bot{token}/getWebhookInfo")
        webhook_url = (hook.get("result") or {}).get("url", "")
    except FetchError:
        webhook_url = ""

    if webhook_url:
        host = webhook_url.split("//")[-1].split("/")[0]
        print(f"This bot has a webhook active ({host}).\n"
              "  Telegram refuses getUpdates while a webhook is set, so this\n"
              "  command cannot find your chat id.\n\n"
              "  DO NOT delete the webhook unless you know what owns it -- doing\n"
              "  so breaks whatever is currently receiving that bot's messages,\n"
              "  and the webhook's secret_token cannot be read back to restore it.\n\n"
              "  Either create a separate bot for FPL reminders (cleanest), or\n"
              "  read the chat id from the other project's config.\n\n"
              "  Sending still works fine with a webhook active -- only this\n"
              "  lookup is blocked. Set TELEGRAM_CHAT_ID and run:\n"
              "    python3 scripts/notify.py --dry-run --force", file=sys.stderr)
        return 1

    try:
        # The token is in the path, so a failure here must not echo the URL.
        updates = http_get(f"{TELEGRAM_API}/bot{token}/getUpdates")
    except FetchError:
        print("error: could not reach Telegram, or the bot token is wrong.\n"
              "  Check the token with:\n"
              "    curl -s https://api.telegram.org/bot<TOKEN>/getMe", file=sys.stderr)
        return 1

    if not updates.get("ok"):
        print(f"error: Telegram rejected the token: {updates.get('description')}",
              file=sys.stderr)
        return 1

    chats = {}
    for update in updates.get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            label = chat.get("title") or chat.get("username") or chat.get("first_name") or ""
            chats[chat["id"]] = f"{chat.get('type', '?')}  {label}".strip()

    if not chats:
        print("No chats found.\n"
              "  Telegram only reveals a chat id after your bot has received a\n"
              "  message. Open a chat with your bot, send it anything, then rerun.\n"
              "  (For a channel, add the bot as an admin and post there.)")
        return 1

    print("Chat ids that have messaged this bot:\n")
    for chat_id, label in chats.items():
        print(f"  TELEGRAM_CHAT_ID={chat_id}    ({label})")
    print("\nAdd the one you want to .env, then:")
    print("  python3 scripts/notify.py --dry-run --force")
    return 0


def compose(brief: dict, urgent: bool) -> str:
    hours = brief["hours_to_lock"]
    when = f"{hours:.0f}h" if hours >= 1 else f"{hours * 60:.0f}min"
    head = (f"‼️ *FPL GW{brief['gw']} — act tonight*"
            if urgent else f"⏳ *FPL GW{brief['gw']} — lock coming up*")
    lines = [
        head,
        "",
        f"*Deadline*  {brief['deadline_syd']}",
        f"*Act by*    {brief['lock_syd']}  ({when} away)",
    ]
    if brief["overnight"]:
        lines.append("_Deadline is overnight in Sydney — act at the lock time, not the deadline._")
    # Set FPL_PROJECT_DIR (in .env locally, or as a GitHub secret) to
    # have the message carry a copy-pasteable cd; otherwise it just shows the
    # command to run once you are in the project.
    project_dir = setting("FPL_PROJECT_DIR")
    command = f"/fpl-manager {'lock — use fpl-scout' if urgent else 'plan'}"
    block = [f"cd {project_dir} && claude", command] if project_dir else [command]
    lines += ["", "```", *block, "```"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print, send nothing")
    parser.add_argument("--force", action="store_true",
                        help="send even outside an alert window (for testing)")
    parser.add_argument("--chat-id", action="store_true",
                        help="print the chat ids that have messaged your bot")
    args = parser.parse_args()

    if args.chat_id:
        token = setting("TELEGRAM_BOT_TOKEN")
        if not token:
            print("error: set TELEGRAM_BOT_TOKEN in .env first (from @BotFather)",
                  file=sys.stderr)
            return 1
        return show_chat_ids(token)

    try:
        bootstrap = http_get(f"{BASE_URL}/bootstrap-static/")
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    event = next_event(bootstrap)
    if not event:
        print("season complete -- nothing to remind about")
        return 0

    brief = deadline_brief(event)
    hours = brief["hours_to_lock"]
    urgent = hours <= URGENT_HOURS

    if hours < 0 and not args.force:
        print(f"GW{brief['gw']} lock time has passed ({hours:.1f}h ago) -- silent")
        return 0
    if hours > HEADSUP_HOURS and not args.force:
        print(f"GW{brief['gw']} lock is {hours:.1f}h away -- outside alert window, silent")
        return 0

    message = compose(brief, urgent)
    if args.dry_run:
        print(f"[dry run] would send ({'urgent' if urgent else 'heads-up'}):\n")
        print(message)
        return 0

    token, chat_id = setting("TELEGRAM_BOT_TOKEN"), setting("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set "
              "(GitHub Secrets, or .env locally)", file=sys.stderr)
        return 1

    try:
        send_telegram(token, chat_id, message)
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"sent {'urgent' if urgent else 'heads-up'} reminder for GW{brief['gw']} "
          f"({hours:.1f}h to lock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
