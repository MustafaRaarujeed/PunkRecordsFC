# Punk Records FC — FPL 2026/27

An agent picks the Fantasy Premier League team each gameweek. A human executes
the changes on the FPL website. The agent's output is an instruction card, not
an essay.

Named for Vegapunk's archive of all the world's knowledge, on the theory that a
team picked by something that reads every stat should be called something.

## The idea

Ask an LLM to "pick a good FPL team" and it produces a plausible one. It will
also invent form, misremember which club a player is at, and recall injuries
from a season that has already finished — confidently, and without showing its
working.

So the model is not asked to pick the team. Instead:

1. **Scripts fetch the data.** Nothing is recalled from memory.
2. **A projection model computes expected points** for all 572 players from
   that data, with a written-down formula.
3. **An integer program picks the squad**, maximising projected points under
   the real constraints (£100.0m, 3 per club, valid formation).
4. **The agent supplies what the API cannot see** — press-conference news,
   rotation risk, tactical role — and audits the result.
5. **A validator refuses to show an illegal squad.**

The agent's judgement enters at defined points, by adjusting inputs. It never
silently swaps a player, because an unexplained swap is indistinguishable from
a hallucination.

## Setup

```bash
git clone <this repo> && cd PunkRecordsFC
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill it in — see Credentials below
./install.sh              # installs the skill and agent into ~/.claude
```

Verify:

```bash
python3 scripts/fetch.py --core
python3 scripts/validate.py --rules      # constants match the live API
python3 scripts/deadlines.py             # next deadline, in Sydney time
```

## Credentials

Everything except `my-team` works with no credentials at all.

Copy `.env.example` to `.env` (gitignored) and fill in what you need. Every
variable is optional — the scripts degrade gracefully and say what they lost.

| Variable | Needed for | How |
|---|---|---|
| `FPL_ENTRY_ID` | Reading your own squad | The number in `/entry/<N>/event/1` when viewing your team. Not secret |
| `ODDS_API_KEY` | Sharper fixture difficulty | Free tier at the-odds-api.com; a weekly pull costs ~4 of 500 |
| `FPL_ACCESS_TOKEN` | `my-team` — bank, selling prices, free transfers | DevTools → Application → Cookies → `access_token`. Lasts ~8h |
| `TELEGRAM_BOT_TOKEN` | Deadline reminders | From [@BotFather](https://t.me/BotFather). **Belongs in GitHub Secrets**; put it in `.env` only to test locally |
| `TELEGRAM_CHAT_ID` | Deadline reminders | From `api.telegram.org/bot<TOKEN>/getUpdates` after messaging your bot |
| `FPL_PROJECT_DIR` | A copy-pasteable `cd` in the reminder | Optional. Your local path |

The Telegram variables are used by `scripts/notify.py`, which normally runs in
GitHub Actions rather than on your machine — see
[Deadline reminders](#deadline-reminders) for the full setup.

### Getting your squad state

`/api/my-team/<id>/` returns bank, purchase prices and free-transfer count — the
one endpoint needing authentication.

**FPL uses bearer auth, not cookies.** Every combination of the browser cookie
jar returns 403; `Authorization: Bearer <access_token>` returns 200. So:

1. Log in to fantasy.premierleague.com
2. DevTools → Application → Cookies → copy `access_token`
3. Put it in `.env` as `FPL_ACCESS_TOKEN`

```bash
python3 scripts/fetch.py --my-team && python3 scripts/sync_squad.py
```

The token lasts about **8 hours**. Grab it when you sit down for a session and
it covers the whole session, letting the agent refetch live rather than working
from a snapshot. `fetch.py` checks expiry locally and reports the time it
lapsed, instead of an opaque 403.

> **Do not store the `refresh_token`.** It sits in the same cookie jar, lasts
> months, and its scope includes `p1:update:user` and `p1:reset:userPassword` —
> an account-takeover credential, not read-only fantasy access. The short-lived
> access token is deliberately the weaker thing to keep on disk.

**No-credentials alternative.** In a logged-in browser open:

```
https://fantasy.premierleague.com/api/my-team/<YOUR_ENTRY_ID>/
```

Save the response to **`data/my-team.json`** — the same path `fetch.py` writes
to, and gitignored — then run `sync_squad.py` with no arguments. `--from-file`
exists only for a file saved somewhere else.

## Timing — read this one

FPL publishes deadlines in UTC. From Sydney, that puts:

| Sydney local deadline | Gameweeks |
|---|---|
| Sun 00:xx | 17 |
| Sat 22:xx | 7 |
| Thu 05:xx | 5 |
| Sat 03:xx | 4 (including GW1) |
| Sat/Sun 23:xx | 5 |

"Act two hours before the deadline" would mean being at a laptop at 01:30 on a
Saturday. So `scripts/deadlines.py` reports a **lock session** — the last civil
evening beforehand — alongside the real deadline.

This costs almost nothing, because Sydney runs 9–11 hours *ahead* of the UK: an
evening session here is UK midday, so Friday press conferences are already in.

**GW1: deadline Sat 22 Aug 03:30 AEST, act by Fri 21 Aug 21:00 AEST.**

DST is handled via `zoneinfo` (AEDT from 4 Oct 2026 to 4 Apr 2027) — never
hardcode an offset.

**Not in Sydney?** Set `FPL_TIMEZONE` in `.env` to your IANA zone (e.g.
`Europe/London`). It defaults to `Australia/Sydney`, and an unrecognised zone
warns rather than silently falling back — a confidently wrong lock time is worse
than none. The overnight-deadline problem is specific to Australia; from the UK
these deadlines are all civilised.

## Weekly routine

```bash
# Early-week planning pass, ~3 days out
python3 scripts/fetch.py --core
python3 scripts/odds.py
# squad state
python3 scripts/fetch.py --my-team && python3 scripts/sync_squad.py
python3 scripts/project.py --horizon 5
.venv/bin/python scripts/optimise.py --transfer --max-transfers 2

# Lock pass, the evening before the deadline
python3 scripts/fetch.py --core --force     # prices move overnight
# ... get team news, rerun project + optimise ...
python3 scripts/validate.py --all
```

Or just ask Claude — the `fpl-manager` skill drives all of the above:

```
/fpl-manager plan     # Tue/Wed, reconnaissance
/fpl-manager lock     # the evening before the deadline, the one that matters
/fpl-manager review   # after the gameweek settles
```

`/fpl-manager draft` builds the initial 15. Add `--reserve 5` thinking if the
draft is days early — a squad spent to exactly £0.0m cannot absorb an overnight
price rise.

## Scripts

| Script | Does | Needs |
|---|---|---|
| `fetch.py` | Pulls and caches API data | stdlib |
| `deadlines.py` | Deadlines in Sydney time, with lock sessions | stdlib |
| `odds.py` | Per-fixture expected goals from bookmaker prices | stdlib + key |
| `project.py` | Expected points per player per gameweek | stdlib |
| `backtest.py` | Replays the model over a finished season | stdlib |
| `fetch_history.sh` | Downloads historical season data | curl |
| `optimise.py` | Picks the squad by integer program | `.venv` (pulp) |
| `validate.py` | Rule and squad-legality checks | stdlib |
| `sync_squad.py` | Writes `state/squad.json` from `my-team` | stdlib |
| `notify.py` | Telegram deadline reminder (runs in CI) | stdlib |

Only `optimise.py` needs the venv. Everything else is stdlib, so a broken
install never blocks a data refresh.

Flags worth knowing:

```bash
python3 scripts/project.py --top 30            # leaderboard
python3 scripts/project.py --disagree 10       # where the model departs from the baseline
python3 scripts/project.py --needs-assumption 3  # players the model cannot see, by club
.venv/bin/python scripts/optimise.py --draft --lock Haaland --exclude Salah
.venv/bin/python scripts/optimise.py --xi      # best XI from the current squad
python3 scripts/backtest.py --season 2024-25 --sweep-blend   # holdout
.venv/bin/python scripts/optimise.py --draft --reserve 5      # hold 0.5m back
```

`--top`, `--disagree` and `--needs-assumption` reuse the cached projections
rather than regenerating them, so a reporting run cannot silently change the
horizon the optimiser then reads. Pass `--horizon` explicitly to recompute.

`fetch.py --players` makes 572 requests (~3.5 min) and caches for 24h. Run it
once before the draft; after that the cache does the work.

## State vs data

- **`state/`** is the source of truth. `squad.json` (the 15, selling prices,
  bank, free transfers), `chip-plan.md`, `priors.md`, `log/gw{N}.md`.
  Never delete it. **Never keep a second copy of it** — two `squad.json` files
  means the agent reads one and writes the other, and the squad silently drifts
  from reality. This is why `install.sh` copies only the skill and agent.
- **`data/`** is a disposable cache, gitignored, fully rebuildable via
  `fetch.py`.

### Decision log

Every gameweek leaves two files in `state/log/`:

| File | Holds | Written by |
|---|---|---|
| `gw{N}-decision.json` | Squad, xP, baseline, transfer gain, flags | `optimise.py`, **automatically** |
| `gw{N}.md` | Why — what was rejected, what would make you wrong | You, from `TEMPLATE.md` |

The split matters. Prose depends on someone remembering, and an agent that
forgets leaves no trace of forgetting — so the numbers are captured
unconditionally and a gameweek can always be audited after the fact, even if the
narrative is missing.

```bash
python3 scripts/validate.py --log    # which gameweeks are missing either half
```

Bank is deliberately excluded from the records so they stay committable.

## The skill and the agent

`install.sh` copies two things into `~/.claude`, substituting `{{PROJECT_ROOT}}`
for this directory's absolute path:

- **`fpl-manager` skill** — four modes: `draft` (initial 15), `plan`
  (early-week), `lock` (pre-deadline), `review` (post-gameweek).
- **`fpl-scout` agent** — gathers team news and odds. It has **no write tools**,
  deliberately: a cold agent that misreads `squad.json` writes a wrong squad
  back, so the main thread keeps the pen.

**These are copies.** After editing anything under `skills/` or `agents/`,
rerun `./install.sh` or the change does nothing.

## Known weaknesses

Documented in full in `skills/fpl-manager/references/projection-model.md`. The
ones that matter:

1. **Players with no Premier League history project near zero.** Promoted-club
   players and new signings are flagged `no_history=1` and the optimiser will
   never pick them. Preseason that is 203 of 572 players. **Review these by hand
   at every draft** — it is the model's biggest blind spot.
   Promoted clubs are the acute case: **97% of Coventry, Hull and Ipswich
   players cannot be modelled.** They are not worthless (47–100% of an
   established club's points per minute, tracking team quality), but their
   minutes are unknowable from data — FPL's preseason pricing predicts them at
   rho 0.175. Assert minutes in `state/minutes-assumptions.json` with evidence;
   the optimiser ignores such players unless you pass `--allow-assumed`.
   A further 24 are flagged `stale=1`: their last PL season is years old, and if
   it predates 2025/26 they have no defensive-contribution data, so DefCon
   scores zero and they are under-projected for a data reason, not a football
   one. `python3 scripts/project.py --disagree 10` shows where the model most
   departs from the plain scoring record, in both directions.
2. **Fixture difficulty is coarse without odds.** `strength_attack_*` and
   `strength_defence_*` are all zero until matches are played, so the model
   falls back to 1–5 overall ratings. Run `scripts/odds.py` first — bookmaker
   prices replace the strength model for every fixture they cover, and
   `project.py` reports the coverage. Odds typically only run 1–2 gameweeks
   ahead, so longer horizons still lean on the fallback.
3. **DefCon is miscalibrated in both directions.** Where the model predicts
   under 10%, players hit 10.6%; where it predicts 81%, they hit 54%.
   Defensive-action counts are overdispersed and Poisson cannot capture that.
   Distrust the most confident DefCon projections most.
4. **New penalty and set-piece takers are invisible.** Check `penalties_order`
   manually.
5. **The model does not beat the baselines.** Ranking players projected to play
   45+ minutes, across two seasons:

   | Predictor | 2025/26 (tuned on) | 2024/25 (holdout) |
   |---|---|---|
   | Model alone | 0.229 | 0.268 |
   | **Model + form blend (ships)** | **0.263** | **0.297** |
   | Points per game alone | **0.324** | **0.338** |
   | FPL's own published xP | 0.135 (broken column) | **0.624** |

   A naive points-per-game baseline ranks better in both seasons, and FPL's own
   xP is far better again on the season where that column is trustworthy. Treat
   xP as one input, not an oracle. Its value is in what a scoring average cannot
   see — fixtures, blanks and doubles, minutes, availability, DefCon.
6. **It over-predicts at the top.** Decile 10 projects 4.95 and delivers 3.89.
   That is where captaincy and hit decisions live, so discount accordingly.
7. **The holdout says nothing about DefCon.** 2024/25 predates the rule and the
   underlying stats were not recorded, so the DefCon term is inert there. It
   remains validated only on a single season.

## Deadline reminders

A GitHub Action pings a Telegram channel when a deadline approaches. It needs
**no FPL credentials** — deadlines are public — and alerts on the *lock session*
rather than the raw deadline, since most deadlines land overnight in Sydney.

### Test it locally first

1. Message [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`, copy the
   token into `.env` as `TELEGRAM_BOT_TOKEN`.
2. **Open a chat with your new bot and send it anything.** Telegram will not
   reveal your chat id until the bot has received a message — this is the step
   everyone misses.
3. Find your chat id:
   ```bash
   python3 scripts/notify.py --chat-id
   ```
   Put it in `.env` as `TELEGRAM_CHAT_ID`.

   > **Reusing a bot from another project?** If it already has a webhook,
   > Telegram blocks `getUpdates` and this lookup cannot work. **Do not delete
   > the webhook** — that breaks whatever currently receives the bot's messages,
   > and its `secret_token` cannot be read back to restore it. Sending is
   > unaffected, so just set `TELEGRAM_CHAT_ID` by hand. A dedicated bot is
   > cleaner.
4. Preview the message without sending:
   ```bash
   python3 scripts/notify.py --dry-run --force
   ```
5. Actually send one:
   ```bash
   python3 scripts/notify.py --force
   ```

`--force` matters: without it the script correctly stays silent whenever the
deadline is far away, which looks like a failure when you are testing.

### Then move it to GitHub

**Settings → Secrets and variables → Actions → New repository secret**, adding
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` — the same values, but they belong
in Secrets rather than `.env` for the scheduled run.

Optionally add `FPL_PROJECT_DIR` (e.g. `~/code/PunkRecordsFC`) so the message
carries a copy-pasteable `cd`. Left unset it just shows the command; the path is
personal and is never hardcoded, since this repo is public.

Verify end to end: **Actions → FPL deadline reminder → Run workflow**, with
*force* ticked.

It runs twice daily and exits quietly outside the alert window (30h and 6h
before the lock). GitHub's scheduler can drift by 10–15 minutes and occasionally
skips runs under load, so treat it as a safety net rather than the only thing
standing between you and a missed deadline.

## Understanding the model

**[docs/model-explained.md](docs/model-explained.md)** explains the whole
approach in plain language: how xP is built, what rho / MAE / RMSE / bias /
calibration / log-loss actually mean, and every constant in the code — what it
does, where its value came from, and how much to trust it. Start there before
changing anything.

## Backtesting

```bash
scripts/fetch_history.sh                    # ~6MB into data/historical/
python3 scripts/backtest.py                 # replay 2025/26, GW6-38
python3 scripts/backtest.py --components    # DefCon and minutes calibration
python3 scripts/backtest.py --tune          # grid-search the constants
```

No lookahead: projecting gameweek N uses only rounds strictly before N, plus the
prior season. Full findings in
`skills/fpl-manager/references/projection-model.md`.

**2025/26 is the tuning season; 2024/25 is an untouched holdout.** `FORM_BLEND`
optimised at exactly 0.5 on both, independently — good evidence the blend is
real rather than fitted noise. Do not tune on the holdout; use it only to check
whether the tuned values hold.

It has already earned its keep, catching four real problems: an inverted defence
multiplier that would have corrupted every projection once matches were played,
a minutes model dividing by appearances instead of gameweeks, a
negative-binomial "improvement" that looked 26% better on component log-loss
while doing nothing end to end, and a broken `xP` baseline column that had
flattered the model's results.

## Verified game facts

Read from the live API on 2026-08-07, not from memory. `validate.py --rules`
re-asserts them on every run.

- Free transfers bank up to **5**
- Chips are available **twice**, once per half; first-half chips expire at GW19
- **DefCon**: +2 at 10 CBIT for defenders, 12 CBIRT for midfielders and
  forwards. `defensive_contribution` is a raw action count, and
  `clearances_blocks_interceptions` excludes tackles despite the name —
  verified against 2025/26 totals (Senesi 357+62=419, Anderson 106+306+103=515)
- The 2026/27 BPS change removed the dispossessed-in-a-tackle penalty, which
  helps dribblers and attacking full-backs

## Credits and caveats

- **The FPL API is undocumented and unofficial.** Endpoint shapes have changed
  between seasons and can change again without notice — which is why
  `validate.py --rules` re-asserts every scoring constant against the live API
  on each run. `fetch.py` rate-limits itself and caches aggressively; please
  keep it that way.
- **Historical backtest data** comes from
  [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League),
  which archives per-gameweek FPL data going back years. Nothing from it is
  redistributed here — `scripts/fetch_history.sh` downloads it on demand.
- **Odds** are from [the-odds-api.com](https://the-odds-api.com) (free tier).
- Not affiliated with the Premier League or Fantasy Premier League. This is a
  personal project, shared in case the approach is useful; no support implied.

## Licence

[MIT](LICENSE). Use it, fork it, adapt it.

Note that the data it fetches is not covered by that licence: the FPL API
belongs to the Premier League, the historical archive is
[vaastav's](https://github.com/vaastav/Fantasy-Premier-League) under its own
terms, and odds are subject to the-odds-api.com's terms of service.

## Status

Built 2026-08-07, before GW1.

- [x] Fetch, projection, optimiser, validator, deadline handling
- [x] Skill, agent, install script
- [x] Odds integration (`odds.py`) — verified live, 10 fixtures priced
- [x] Backtesting against 2025/26, with 2024/25 as an untouched holdout —
      4 real problems found and fixed
- [x] Model documentation (`docs/model-explained.md`)
- [x] Telegram deadline reminder via GitHub Actions — secrets set, workflow
      verified end to end
- [x] FPL account created and `.env` filled in
- [ ] GW1 squad drafted and entered
- [ ] Re-validate in-season: the `strength_attack/defence` branch has never run
      on live data (those fields are zero preseason)
