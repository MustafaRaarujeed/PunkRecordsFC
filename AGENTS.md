# AGENTS.md

## What this is

**Punk Records FC** — an agent picks the Fantasy Premier League team each
gameweek; a human executes the changes on the FPL website. The output is a
short instruction card, not an essay.

The whole point is that **the model never picks the squad by judgement**.
Scripts fetch data, a projection model computes expected points, and an integer
program picks the squad under the real constraints. An LLM asked to rank
footballers produces a fluent ranking unconnected to evidence, so judgement is
confined to defined places: adjusting inputs, and auditing outputs.

## Doing the actual FPL work

**Invoke the `fpl-manager` skill.** Do not improvise a gameweek from this file —
it has four modes (`draft`, `plan`, `lock`, `review`), hard anti-hallucination
rules, and the output format. This file is orientation only.

For team news, spawn the `fpl-scout` agent — it has **standing permission** in
`plan`, `lock` and `review` runs (granted 2026-08-08), so do not stop to ask.
Any other agent, or a `draft` run, still needs the user's say-so.

The user may keep a local, untracked `PROMPTS.md` of copy-paste prompts. Do not
recreate or track it — it holds their local path, and this repo is public.

The skill and agent are **copies** installed into the configured agent directory
by `./install.sh`. Edit the originals under `skills/` and `agents/`, then rerun
`./install.sh` — editing the installed copy does nothing.

## Layout

```
scripts/     fetch, odds, project, optimise, validate, backtest,
             deadlines, sync_squad, notify, fetch_history.sh
state/       source of truth: squad, chip plan, priors, minutes
             assumptions, decision logs
data/        disposable API cache, gitignored, rebuilt by scripts/fetch.py
docs/        model-explained.md -- the statistics and every constant
skills/      the fpl-manager skill (source of the installed copy)
agents/      the fpl-scout agent (source of the installed copy)
.github/     deadline-reminder.yml -- Telegram alerts via Actions
```

Only `optimise.py` needs the venv (`.venv/bin/python`, for pulp). Everything
else is stdlib, so a broken install never blocks a data refresh.

## Things that will trip you up

- **All times to the user in their local timezone.** FPL publishes deadlines in
  UTC, and in Sydney 26 of 38 land overnight. Never quote a bare UTC deadline.
  Run `python3 scripts/deadlines.py`, which reports the deadline and the last
  civil evening to act. The zone is `FPL_TIMEZONE` in `.env`, defaulting to
  `Australia/Sydney`.
- **`my-team` uses bearer auth, and the token expires every ~8 hours.**
  `FPL_ACCESS_TOKEN` in `.env`. When it lapses, `fetch.py` says so with the
  exact time — ask the user for a fresh one (DevTools → Application → Cookies →
  `access_token`) rather than working from stale squad state. Cookies do not
  authenticate this endpoint at all; there is no cookie fallback.
- **Transfer mode refuses before the first deadline.** Squad changes are
  unlimited and free until GW1, so incremental transfer logic does not apply —
  use `--draft`. As of 2026-08-09 `state/squad.json` holds **FPL's auto-pick**,
  not a chosen squad; do not treat it as a starting position.
- **`state/squad.json` is the single source of truth** and is gitignored (it
  holds bank and purchase prices). Never guess the squad. If it is missing or
  older than the last deadline, say so and stop.
- **This repo is public.** Never commit credentials, and never put the user's
  personal state in a tracked file. `.env`, `state/squad.json`, `data/` and
  `PROMPTS.md` are ignored. Ask if unsure.
- **The model does not beat a naive baseline.** Points-per-game out-ranks it in
  both backtested seasons. `projections.csv` carries `ppg_horizon` and `xp_edge`
  alongside every projection for exactly that reason — treat xP as one input.
- **Transferred players carry their old club's minutes record.** Flagged
  `new_club=1`; `project.py` names the highly-rated ones. The club assignment
  itself is authoritative — the question is whether he starts, not where he
  plays.
- **204 of 573 players cannot be modelled** preseason (promoted clubs, new
  signings), plus 24 with stale history. They are flagged `no_history` and
  `stale`. The optimiser cannot see them unless a human asserts minutes in
  `state/minutes-assumptions.json`, and even then only with `--allow-assumed`.
  This needs a human every draft.

## The decision log

Every gameweek leaves two files in `state/log/`:

- `gw{N}-decision.json` — squad, xP, baseline, transfer gain, flags. Written by
  `optimise.py` **automatically, on every run**. You do not have to do anything.
- `gw{N}.md` — *why*: what was rejected and by how much, what the model could
  not see, what would make the call wrong. **You write this**, from
  `state/log/TEMPLATE.md`.

`validate.py --log` reports gameweeks missing either half. The split exists
because prose depends on someone remembering, and an agent that forgets leaves
no trace of forgetting.

## Verified facts go stale — re-test them

This has bitten twice, both times invisibly until something was actually run:

- `fetch.py --force` passed `max_age=None`, which `read_cache` treats as *never
  expires* — so it guaranteed a cache hit, the exact opposite of forcing. The
  lock procedure's price refresh had been doing nothing at all.
- "FPL's SSO cannot be scripted" was recorded as a settled decision. It was
  wrong: cookies return 403, but `Authorization: Bearer <access_token>` works.

When a doc asserts something about an external API — **especially if it explains
why something is impossible** — check it rather than inheriting it.

## Verifying a change

```bash
python3 scripts/validate.py --rules      # constants still match the live API
python3 scripts/project.py --horizon 6
.venv/bin/python scripts/optimise.py --draft
python3 scripts/backtest.py --season 2025-26
```

`backtest.py --season 2024-25` is a **holdout**. Use it to check whether tuned
values hold; never tune on it.
