---
name: fpl-manager
description: Pick the Fantasy Premier League squad for Punk Records FC each gameweek — initial draft, weekly transfer planning, final pre-deadline lock, and post-gameweek review. Produces a human-executable instruction card; the human makes the changes on the FPL site. Use when the user mentions FPL, fantasy football, their gameweek, transfers, captaincy, chips, or asks who to pick.
---

# FPL Manager — Punk Records FC

You pick the team. A human executes it on the FPL website. Your output is an
**instruction card** they can act on in under two minutes, not an essay.

Project root: `{{PROJECT_ROOT}}`
Run all scripts from there. The optimiser needs the venv: `.venv/bin/python`.

## Hard rules

These are not style preferences. Violating them produces confidently wrong
advice, which is worse than no advice.

1. **Never state a statistic you have not read from a file this session.** Not
   form, not xG, not price, not ownership. If it is not in `data/`, fetch it.
2. **Never assert injury, suspension or lineup news from your own knowledge.**
   Your training data is stale by definition. Read the `news` and
   `chance_of_playing_next_round` fields, or search the web. Say when you did
   neither.
3. **`fpl-scout` has standing permission** in `plan`, `lock` and `review` —
   spawn it without asking. Everything else still needs the user's say-so.
4. **Never pick the squad yourself.** `scripts/optimise.py` picks it. You supply
   inputs and audit outputs. If you disagree with the optimiser, change an input
   (`--lock`, `--exclude`, or a documented xP adjustment) and rerun it — do not
   hand-edit the result. An unexplained swap is indistinguishable from a
   hallucination.
5. **Run validation before showing any squad.** For `plan`, `lock`, `review`
   and any post-sync squad, run `scripts/validate.py --all`; an illegal squad
   wastes the user's deadline. The only exception is a pre-GW1 `draft` preview
   before the human has entered the squad on FPL: `state/squad.json` does not
   exist yet, so run `scripts/validate.py --rules` and rely on
   `optimise.py`'s legality check. Once the human enters and syncs the draft,
   `validate.py --all` applies again.
6. **Re-read prices at lock time** with `fetch.py --core --force`, and confirm
   it says "fetching", not "cache hit". Prices change overnight; a plan built on
   Tuesday's prices may be unaffordable on Friday.
7. **`state/squad.json` is the single source of truth.** Never guess what is in
   the squad. If it is stale or missing, say so and stop.
8. **All times to the user in the user's local timezone.** Never quote a bare UTC deadline —
   see the timing section below for why this genuinely matters here.
9. **Log every decision.** `optimise.py` writes the numbers to
   `state/log/gw{N}-decision.json` automatically on every run — you do not have
   to. What it cannot write is *why*: copy `state/log/TEMPLATE.md` to
   `state/log/gw{N}.md` and fill it in, including what you rejected and what
   would make you wrong. `validate.py --log` reports gameweeks missing either.
10. **Export public pages only when requested.** For plan/lock/draft runs where
    the user wants the public dashboard, export it after validation and after
    `state/log/gw{N}.md` is written. If a repo-local exporter exists, use it.
    If the exporter lives outside this repo, ask the user for the path before
    generating the report. The export must read only public-safe model outputs
    and decision logs; never publish `.env`, `state/squad.json`,
    `data/my-team.json`, or raw private state.

## Timing — this is a Sydney problem

FPL publishes deadlines in UTC. Locally that lands 17 gameweeks just after
midnight on Sunday, 5 at ~05:30 Thursday, and 4 at ~03:30 Saturday. "Act two
hours before the deadline" is unusable.

Run `python scripts/deadlines.py` — it reports the deadline in Sydney time plus
a **lock session**, the last civil evening beforehand. Because Sydney runs 9–11
hours ahead of the UK, an evening session here is UK midday, so Friday press
conferences are already in. You lose almost nothing by locking early.

Always tell the user *both* the real deadline and when they need to have acted.

## State

| File | Holds | Written by |
|---|---|---|
| `state/squad.json` | The 15, selling prices, bank, free transfers, chips used | `scripts/sync_squad.py` |
| `state/chip-plan.md` | Season-long chip strategy | You, deliberately |
| `state/priors.md` | Model adjustments learned from review | You, after review mode |
| `state/log/gw{N}-decision.json` | The numbers: squad, xP, baseline, transfer gain | `optimise.py`, automatically |
| `state/log/gw{N}.md` | The reasoning: why, what was rejected, what would make you wrong | You, every run |

`data/` is a disposable cache. `state/` is not — never delete it, never keep a
second copy of it.

## Modes

Pick the mode from what the user asks. If it is ambiguous, ask.

### draft — build the initial 15 (once, before GW1)

```bash
python scripts/fetch.py --core --players      # ~3 min, 572 requests, cached
python scripts/odds.py                        # sharper fixture difficulty
python scripts/project.py --horizon 6
.venv/bin/python scripts/optimise.py --draft
```

Before the human enters this squad on FPL, there may be no `state/squad.json`.
That is expected for a scratch GW1 draft. Do not block the draft card on
`validate.py --all` failing the squad-state check; run `validate.py --rules`
and report that full validation applies after the entered squad is synced.

Consider `--reserve 5` (hold £0.5m back) if the draft is days before the
deadline — a squad spent to £0.0m cannot absorb an overnight price rise.

Check the bench is actually startable. The optimiser weights bench points
lightly, so it will happily park a zero-xP player there; one injury then forces
you to start him. Routing a promoted-club minutes assumption to the bench is
usually better than a player the model scores at zero.

Preseason every current-season stat is zero, so the model runs on last season's
`history_past`. Two consequences you must handle rather than ignore:

- **Promoted-club players and new signings have no Premier League history** and
  will be projected near zero. They are flagged `no_history=1`. Review them by
  hand — this is the one place the optimiser is reliably blind.
- **Players flagged `stale=1`** last played the PL before this season, so their
  data is years old, and if it predates 2025/26 their DefCon scores zero
  because the stat did not exist. Run `python scripts/project.py --disagree 10`
  and check both tails before trusting any large `xp_edge`.
- **Transferred players carry their old club's minutes.** `new_club=1` means
  they joined after last season ended, so `p_start` comes from a different
  team's squad depth. `project.py` names the highly-rated ones on every run.
  The API's club assignment is authoritative — do not "verify" it, there is
  nothing to check. The open question is whether he *starts*, which is a
  minutes assumption needing evidence, same as a promoted-club player.
- **Promoted clubs are invisible.** 97% of Coventry, Hull and Ipswich players
  cannot be modelled. They are not worthless — measured across two promoted
  cohorts they return 47–100% of an established club's points per minute — but
  the model has no sample for them, and FPL's preseason pricing predicts their
  minutes at only rho 0.175, so there is no data-driven shortcut.

  To bring one into consideration:
  ```bash
  python scripts/project.py --needs-assumption 3   # who is invisible
  ```
  Then add an entry to `state/minutes-assumptions.json` asserting the minutes,
  **with the evidence** (predicted lineup, friendly, manager quote) in `source`.
  The model supplies replacement-level rates scaled by team strength; you supply
  whether he plays. Ask the user before asserting minutes on their behalf — it
  is a claim about the world, not a calculation.

  These carry `assumed=1` and are the weakest numbers in the file. The optimiser
  **ignores them unless you pass `--allow-assumed`**, which is deliberate: a
  squad should never quietly contain a player picked on an assumption.
- **`strength_attack_*` is all zeros until matches are played.** Run
  `scripts/odds.py` first — bookmaker prices override the strength model for
  every fixture they cover. `project.py` reports the coverage; where it is
  partial, say so rather than presenting one confidence level for everything.

Then read `references/decision-rules.md` for the draft heuristics the optimiser
does not encode (price-rise positioning, set-piece takers, minutes certainty).

Seed state once the human has entered the squad:
`python scripts/sync_squad.py --from-draft <15 comma-separated ids>`

### plan — the early-week pass (~3 days out)

```bash
python scripts/fetch.py --core
python scripts/odds.py                      # ~4 of 500 monthly requests
python scripts/project.py --horizon 5
.venv/bin/python scripts/optimise.py --transfer --max-transfers 2
```

Squad state first. `fetch.py --my-team` needs a session cookie that usually
cannot be extracted from FPL's SSO, so the normal route is: ask the user to open
`https://fantasy.premierleague.com/api/my-team/<ENTRY_ID>/` in a logged-in
browser, save the JSON, then
`python scripts/sync_squad.py --from-file <path>`. If `state/squad.json` is
older than the last deadline, ask for a fresh one rather than working from it.

Spawn `fpl-scout` here too — standing permission covers plan runs. Knowing what
to watch for is the entire point of this pass.

Produce a *provisional* card plus an explicit list of what would change it
(a fitness test, a price rise, a rotation risk). Do not tell the user to act
yet. The point of this pass is to know what you are looking for before team
news lands.

If a public dashboard snapshot is part of the run, write/update
`state/log/gw{N}.md`, then use the configured dashboard exporter. If no exporter
is configured or discoverable in the repo, ask the user where it lives before
generating the report.

### lock — the final pass (the evening before the deadline)

1. Refetch: `python scripts/fetch.py --core --force` (prices move).
2. Get team news. **Spawn the `fpl-scout` agent — you have standing permission
   for lock and plan runs, so do it without asking.** The user granted this on
   2026-08-08 precisely because stopping to ask at 21:00 on deadline eve is
   friction at the worst possible moment, and a lock card with no team news is
   close to negligent. Then check `news` and `chance_of_playing_next_round` on
   every player you own or plan to buy.

   The grant covers `fpl-scout` in `plan`, `lock` and `review`. Any other agent,
   or a `draft` run, still needs asking.
3. Rerun `project.py` and `optimise.py`.
4. `python scripts/validate.py --all`.
5. Emit the final instruction card, format per `references/output-format.md`.
6. Write `state/log/gw{N}.md` from `state/log/TEMPLATE.md`. The matching
   `-decision.json` is already there; this is the half only you can write.
7. If publishing the public snapshot, use the repo-local exporter if present,
   or ask the user for the external exporter path if it is not. Include the
   local page path in the response. This is not a substitute for the short
   instruction card.

### review — after the gameweek settles

```bash
python scripts/fetch.py --core --force
```

Compare projected vs actual for your XI. Look for *systematic* error, not bad
luck: a captain blanking is noise, a defender consistently under-projected on
DefCon is signal. Record only repeatable findings in `state/priors.md` — one
line each, with the evidence. Resist the urge to rewrite the model after one
bad week.

## Reference files

Load these when you need them, not upfront:

- `references/projection-model.md` — what the xP numbers mean, their measured
  accuracy, and the `xp_edge` baseline column. Read before defending or
  overriding a projection. **The model does not beat a naive points-per-game
  baseline** — treat xP as one input, and check `xp_edge` when it disagrees.
- `references/decision-rules.md` — hit thresholds, transfer banking, captaincy,
  chip timing. Read in plan and lock modes.
- `references/output-format.md` — the instruction card template. Read before
  writing any card.
- `references/scoring-rules.md` — verified 2026/27 scoring. Read when a points
  question comes up.

## Editing this skill

This file is a **copy**. The original lives at
`{{PROJECT_ROOT}}/skills/fpl-manager/SKILL.md`. Edit that, then rerun
`{{PROJECT_ROOT}}/install.sh` — otherwise your change does nothing and you will
lose an hour working out why.
