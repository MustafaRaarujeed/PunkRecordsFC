# How the model works, and what every number in it means

A plain-language guide to the projection model, the statistics used to test it,
and every constant in the code — what it does, where its value came from, and
how much to trust it.

Written for someone who wants to understand or change the model without taking
the numbers on faith.

---

## 1. What the model is actually trying to do

For every player, for every upcoming gameweek, produce one number: **expected
points (xP)**.

Not "how many points will he score" — nobody can know that. Expected points is
the *average* he would score if that gameweek were replayed hundreds of times.
He might blank, he might haul; xP is the centre of that distribution.

That distinction matters. A projection of 6.0 that returns 2 is not necessarily
wrong. It is wrong only if, over hundreds of such projections, the average
comes out well below 6.0.

### Why a model instead of just asking the AI

An LLM asked to rank footballers produces a ranking that is fluent, stable, and
unconnected to evidence. It cannot show its working, and it quietly mixes in
training data from seasons that have already finished.

So the model exists to make every recommendation traceable: xP comes from a
formula, the formula's inputs come from a file, and the file came from an API
call made this session. Judgement still matters — it just enters at defined
points (adjusting inputs, spotting what data cannot see) rather than by
silently reordering the output.

---

## 2. The pipeline

```
  fetch.py     API -> data/           (bootstrap, fixtures, per-player history)
  odds.py      bookmaker prices -> expected goals per fixture
  project.py   history + fixtures -> xP per player per gameweek
  optimise.py  xP -> the best legal 15, XI and captain
  validate.py  refuses to show an illegal squad
  backtest.py  replays a finished season to check any of this works
```

### How one player's xP is built

Working from the inside out, for a single fixture:

**Step 1 — how much will he play?**
Everything else scales off this. A brilliant player who plays 20 minutes beats
nobody. From history: `p_start` (share of games started) and `xmins` (average
minutes per gameweek, counting games he missed as zero). Both scaled by
availability — injured, suspended and unavailable players go to zero.

**Step 2 — how good is the fixture?**
Expected goals for both sides. Best source is bookmaker odds; failing that,
team strength ratings. Explained in §5.

**Step 3 — convert to points.**
Each scoring route separately:

| Route | How |
|---|---|
| Appearance | 2 pts if he plays 60+, 1 if he appears at all |
| Goals | his xG per 90 × minutes × fixture quality × points-per-goal for his position |
| Assists | same shape, × 3 points |
| Clean sheet | probability the opponent fails to score, × clean-sheet points |
| Goals conceded | −1 per 2 conceded, for keepers and defenders |
| Saves | keepers only, 1 point per 3 saves |
| Defensive contribution | probability he hits the action threshold, × 2 |
| Bonus | his historical bonus per 90 × minutes |
| Cards | his yellow-card rate, subtracted |

**Step 4 — blend with what he actually scores.**
The steps above rebuild points from components, which drifts. So the result is
averaged with his observed points-per-gameweek. See `FORM_BLEND` in §6 — this
was the single biggest measured improvement.

Doubles and blanks need no special handling: the model sums over however many
fixtures a team has that gameweek, so a blank scores zero and a double counts
twice.

---

## 3. The statistics jargon

Everything used in the backtest output, in plain terms.

### rho (ρ) — Spearman's rank correlation

**Does the model put players in the right order?**

Rank every player by projected points. Rank them again by what they actually
scored. Correlate the two lists of *ranks* — not the raw numbers.

- `1.0` — perfect ordering
- `0.0` — the ranking is worthless
- `−1.0` — perfectly backwards

This is the headline metric because every real FPL decision is a comparison:
which of these two do I buy, who do I captain, which 11 start. You never need
to know Haaland will score exactly 6.6 — you need to know he beats Watkins.

**Low values are normal here.** One gameweek of FPL scoring is mostly noise:
most players return 1–2 points, and the difference between a good pick and a
bad one is often a single goal. FPL's own published xP scores 0.135 on our test
set. So read rho *relative to other predictors on the same data*, never against
an absolute standard.

### MAE — mean absolute error

**On average, how far off is the number?**

Average of |predicted − actual|. An MAE of 2.4 means the projection is out by
about 2.4 points per player per gameweek. Easy to interpret, and it treats all
errors evenly.

### RMSE — root mean squared error

**How far off, with big misses punished harder?**

Square the errors, average, square-root. Because errors are squared, one
6-point miss hurts more than three 2-point misses. Use it when large errors are
disproportionately costly — captaining someone who blanks, for instance.

RMSE is always ≥ MAE. A big gap between them means the errors are uneven: mostly
close, with occasional disasters.

### bias

**Does it lean high or low?**

Mean predicted minus mean actual. Unlike MAE and RMSE, the sign is the point.

- `+0.50` — over-predicts by half a point per player per gameweek
- `0.00` — no systematic lean (errors still exist, they just cancel)

Bias matters most for the hit rule. If you take a −4 when the model says you
gain 5 points, but the model runs +0.5 high on both players, the real gain is
smaller than it looks.

### calibration

**When it says 4 points, do you get 4 points?**

Sort predictions into ten buckets, then compare each bucket's mean prediction
against its mean actual. A well-calibrated model tracks the diagonal.

Ours does not at the top: decile 10 projects 4.95 and delivers 3.89.
Ranking and calibration are different properties — a model can order players
perfectly while being uniformly 20% too high.

### log-loss

**How good are the probabilities, punishing confident mistakes hardest?**

Used only for yes/no events like "did he hit the DefCon threshold". Being 95%
confident and wrong is penalised far more than being 55% confident and wrong.
Lower is better.

**A trap worth knowing.** Log-loss is minimised by a well-calibrated *constant*
predictor. Saying "everyone has a 20% chance" scores well while being useless
for choosing between players. This actually happened during development: a
negative binomial scored 26% better on DefCon log-loss and was rejected because
it did nothing end-to-end. **Always tune against the metric you care about, not
a component proxy.**

### Poisson distribution

Models "how many times does a rare-ish thing happen in a fixed window" —
goals in a match, tackles in 90 minutes. One parameter, the mean.

Used here for clean-sheet probability (`P(opponent scores 0) = e^−xG`),
expected goals conceded, and DefCon thresholds.

Its defining property: **variance equals the mean.** Which is also its weakness.

### overdispersion, and the negative binomial

Real-world counts are usually *more* variable than Poisson allows. A midfielder
averaging 11 defensive actions doesn't produce 10–12 every week — he produces 4
in one game and 18 in the next, depending on game state, opponent and role.
Variance exceeds the mean. That is overdispersion.

The consequence is visible in the backtest: Poisson **under**-predicts the low
band and **over**-predicts the high band. Both tails are fatter than it expects.

The negative binomial fixes this with a second parameter (`shape`) controlling
how fat the tails are — smaller means fatter, and infinity recovers Poisson.
It's implemented (`nbinom_at_least`) and currently switched **off**, because it
didn't improve end-to-end accuracy. See `DC_SHAPE` in §6.

### de-vigging (odds only)

Bookmaker prices include their margin, so implied probabilities sum to more than
100%. De-vigging scales them back to 1.0. Without it, everything is inflated by
5–8%.

### supremacy (odds only)

The expected goal *difference* between two sides. Combined with expected total
goals, it recovers each team's expected goals:
`home = (total + supremacy) / 2`, `away = (total − supremacy) / 2`.

---

## 4. Game rules — not tunable

These are facts about FPL, read from the API's own `game_config` and re-asserted
on every run by `validate.py --rules`. **Never edit these to change model
behaviour.** If one is wrong, the API changed and the model is now broken.

| Constant | Value | Meaning |
|---|---|---|
| `SQUAD_SIZE` | 15 | 2 GKP, 5 DEF, 5 MID, 3 FWD |
| `BUDGET` | 1000 | £100.0m, in tenths |
| `TEAM_LIMIT` | 3 | Max players per club |
| `MAX_FREE_TRANSFERS` | 5 | Banking cap |
| `GOAL_PTS` | GKP 10, DEF 6, MID 5, FWD 4 | Points per goal |
| `CS_PTS` | GKP 4, DEF 4, MID 1, FWD 0 | Clean sheet, needs 60 mins |
| `ASSIST_PTS` | 3 | All positions |
| `DC_PTS` | 2 | Defensive contribution, once per match |
| `DC_THRESHOLD` | DEF 10, MID/FWD 12 | Actions needed. DEF counts clearances + blocks + interceptions + tackles; MID/FWD add recoveries |

---

## 5. Physical constants — reality, roughly

Not FPL rules, but not free parameters either. They describe football.

### `LEAGUE_AVG_GOALS = 1.42`

Goals per team per match in a typical Premier League season (~2.8 per game
total). The baseline every expected-goals calculation scales from.

*Source:* long-run Premier League average. Stable across seasons; leave alone.

### `HOME_ADV = 1.10`

Home teams score about 10% more, away teams about 10% fewer. Applied as a
multiplier and divisor respectively.

*Source:* long-run average. Home advantage has been shrinking over the last
decade, so this may be slightly generous, but it is not a big lever. Overridden
entirely wherever bookmaker odds exist — the odds price home advantage properly
per fixture.

---

## 6. Tuned constants — where the judgement lives

**These are the ones to question.** Each says what it does, where the value came
from, and how much to trust it.

### `FORM_BLEND = 0.5` ⭐ measured

**What it does.** How much to weight the structural model versus the player's
observed points per gameweek. `0.0` = pure model, `1.0` = pure scoring rate,
`0.5` = even split.

**Why it exists.** The component model rebuilds points from xG, minutes, clean
sheets and so on. That's powerful — it sees fixtures and minutes that a raw
scoring average cannot — but it accumulates error at every step. A player's
actual points-per-game is blunt but unbiased. Blending beats either alone.

**Where the value came from.** Backtested on 2025/26 GW6–38:

| Weight | rho (decision-relevant) |
|---|---|
| 0.0 (model only) | 0.229 |
| 0.3 | 0.258 |
| **0.5** | **0.263** |
| 0.7 | 0.258 |

Flat plateau between 0.4 and 0.6; 0.5 sits in the middle.

**How much to trust it.** Moderately. It is the largest measured improvement in
the model, but it was fitted on the same single season it was scored on. Real
out-of-sample value is smaller than the table implies.

### `DC_DISPERSION = 0.90` ⚠️ still a guess

**What it does.** Multiplies the Poisson probability of hitting the DefCon
threshold. At 0.90 it shaves 10% off.

**Why it exists.** Poisson over-predicts for players sitting just above their
threshold, because it assumes less variance than reality.

**Where the value came from.** Nowhere — it was a hand-picked guess before any
backtesting, and the backtest showed the problem is not a simple scaling. Where
the model predicts under 10%, players actually hit 10.6% (under-predicting);
where it predicts 81%, they hit 54% (over-predicting). **A single multiplier
cannot fix an error that runs in both directions.**

**How much to trust it.** Low. Sweeping 0.7–1.3 moved end-to-end rho by under
0.01, so it barely matters — but the DefCon component itself is unreliable near
the threshold. Distrust confident DefCon projections most.

### `DC_SHAPE = 0.0` (disabled) — deliberately rejected

**What it does.** Negative-binomial shape for DefCon counts. `0` falls back to
Poisson × `DC_DISPERSION`.

**Why it's off.** Fitting it gave shape 0.2 and a **26% better component
log-loss** — which looked like a clear win. End-to-end it moved rank correlation
by +0.014 while making bias *worse*. The apparent gain was the log-loss trap
from §3: the fitted distribution compressed almost every player into "about 18%
likely", which is well calibrated on average and useless for ranking. It also
badly under-rated the reliable DefCon defenders that are the whole point.

**Kept in the code as a warning.** Re-enable only with an end-to-end improvement
to show for it.

### `STRENGTH_K = 0.35` ⚠️ untested

**What it does.** How hard a team's 1–5 strength rating bends expected goals.
A 5-rated team gets ×1.35 attack and ×0.65 on goals conceded.

**Where it came from.** Judgement. It produces a plausible spread between best
and worst teams.

**How much to trust it.** Low, but it matters less than it looks: it is only
used in the **preseason fallback**, when `strength_attack_*` is still zero and
no odds are available. Run `odds.py` and this is bypassed for every priced
fixture.

### `APPEAR_UPLIFT = 1.25` ⚠️ weakly tested

**What it does.** Converts probability-of-starting into probability-of-appearing.
A player starting 60% of games is assumed to feature in 75%, the extra being
substitute appearances.

**Where it came from.** Judgement. Sweeping 1.0–1.4 in the backtest barely moved
anything, so it is not a sensitive parameter.

### `BLEND_MINUTES = 900`

**What it does.** How much of the current season must accumulate before it fully
displaces last season. At 900 minutes (~10 full matches) the current season
carries 100% weight; at 450 it is a 50/50 blend.

**Where it came from.** Judgement — roughly the point at which a sample stops
being noise. Not swept.

### `no_history` threshold = 180 minutes

Under two full matches of history is not a usable sample. Those players are
flagged `no_history=1` and never selected by the optimiser. **Preseason that is
203 of 572 players** — every promoted-club player and new signing. This is the
model's single biggest blind spot and needs a manual pass at every draft.

---

## 7. Decision constants — risk appetite, not prediction

These live in `optimise.py` and encode how aggressively to act. They are
*preferences*, not estimates, and cannot be validated by backtesting the way xP
can.

### `MIN_GAIN = 1.5`

Minimum net xP gain before recommending a transfer at all.

Exists because a maximiser always finds *some* marginal move — during testing it
happily proposed a transfer worth **+0.1 xP**, inside the model's own error bars,
burning a transfer worth more banked. Below this threshold, hold.

### `HIT_COST = 4` and the −4 rule

The point cost of an extra transfer is fixed by FPL. The *policy* — take a hit
only when the projected gain exceeds 6.0 (the 4-point cost plus a 2.0 buffer) —
lives in `decision-rules.md`.

The buffer is not timidity. It is a certain loss against an uncertain gain, and
the model over-predicts at the top decile by about 1 point, which is exactly
where hit candidates sit.

### `BENCH_WEIGHT = 0.12`

How much bench players count in the optimiser's objective. Near zero would fill
the bench with the cheapest non-players; too high wastes money on a bench that
rarely plays. 0.12 keeps the bench functional without over-investing.

*Judgement, untested.*

---

## 8. Reading the output against the baseline

Because the naive baseline out-ranks the model, `projections.csv` carries it in
every row rather than hiding it:

| Column | Meaning |
|---|---|
| `xp_horizon` | The model's projection over the horizon |
| `ppg_horizon` | Points-per-gameweek baseline over the same fixtures |
| `xp_edge` | `xp_horizon − ppg_horizon` |
| `stale` | 1 if the player's last PL season is not the most recent |

`xp_edge` near zero means the model and the player's scoring record agree — the
projection is well supported. A large edge is a **claim** the model is making,
and it is worth knowing which kind:

- **Positive** — backing a player against his record. Kind fixtures, a double
  gameweek, rising minutes, or underlying numbers the points have not caught up
  with.
- **Negative** — fading a proven scorer. Hard fixtures, a blank, rotation risk
  — or missing data.

```bash
python3 scripts/project.py --disagree 10
```

That view paid for itself immediately. It surfaced Furlong and Ajayi at edges
near −5, which turned out to have nothing to do with football: both last played
the Premier League in **2020/21**, before defensive contributions were recorded,
so their `dc90` is 0 and the DefCon term silently scores nothing. That is what
the `stale` flag now marks — 24 players preseason, mostly promoted clubs.

**Always check `stale` before acting on a large edge.**

## 9. Promoted clubs, and players with no history

Preseason, 203 of 572 players have no usable Premier League sample, including
**97% of Coventry, Hull and Ipswich**. They project at zero and the optimiser
cannot see them.

They are not worthless. Measured across the two most recent promoted cohorts:

| Cohort | GK | DEF | MID | FWD |
|---|---|---|---|---|
| 2025/26 (Leeds, Burnley, Sunderland) | 0.95 | 0.86 | 0.94 | 0.97 |
| 2024/25 (Ipswich, Leicester, Southampton) | 0.74 | **0.54** | 0.75 | 0.78 |

Promoted-club players return **47–100%** of an established club's points per
minute. A single "promoted discount" constant is therefore indefensible — and
unnecessary, because the spread is explained by team quality:

| Team | Goals against/game | DEF ratio |
|---|---|---|
| Sunderland | 1.26 | 1.00 |
| Leeds | 1.47 | 0.90 |
| Burnley | 1.97 | 0.67 |
| Leicester | 2.11 | 0.54 |
| Ipswich | 2.16 | 0.47 |

Defender returns track goals conceded almost exactly, because defender points
are mostly clean sheets — and the model **already knows** each team's expected
goals against, from bookmaker odds. A blanket constant would double-count it.

### What the model can and cannot supply

- **How much he scores when he plays** — estimable. Replacement-level per-90
  rates (the median among 900+ minute starters), with attacking output scaled by
  the team's attack rating and the baseline scaled by attack or defensive
  solidity depending on position.
- **Whether he plays at all** — **not estimable.** No PL minutes exist, and
  FPL's own preseason pricing predicts eventual minutes at rho **0.175** for
  these players, with bands that are not even monotonic. There is no shortcut.

So minutes are asserted by a human in `state/minutes-assumptions.json`, with the
evidence recorded. No entry means no projection — deliberately.

### Safety properties

1. Assumed projections carry `assumed=1`.
2. `ASSUMED_DISCOUNT = 0.85` is applied, because replacement rates are a median
   over *survivors* (players who got 900+ minutes), and because midfield and
   forward returns sat at ~0.85 of established across both cohorts even after
   team quality.
3. **The optimiser ignores them unless `--allow-assumed` is passed.** A squad
   should never quietly contain a player selected on an assumption.

```bash
python3 scripts/project.py --needs-assumption 3   # who is invisible, by club
```

Revisit after GW3–4, when real 2026/27 minutes exist and these players get
modelled from evidence instead.

## 10. How to re-tune anything

```bash
scripts/fetch_history.sh                    # historical data, ~6MB
python3 scripts/backtest.py                 # baseline scores
python3 scripts/backtest.py --components    # DefCon and minutes calibration
python3 scripts/backtest.py --tune          # sweep the constants
```

Rules to follow:

1. **Judge on end-to-end accuracy**, never on a component in isolation. The
   `DC_SHAPE` episode is what happens otherwise.
2. **Check rho, RMSE and bias together.** A change that lifts rho while
   worsening bias may be a bad trade — bias is what the hit rule depends on.
3. **Beat the baselines or don't ship it.** `backtest.py` prints points-per-game
   and FPL's own xP alongside. Complexity that loses to a scoring average is
   not worth carrying.
4. **Watch for in-sample flattery.** Every constant here was tuned on one
   season. The more you tune, the more you fit that season's noise.

---

## 11. Honest summary of where this stands

Backtested on 2025/26 GW6–38, no lookahead, ranking players projected to play
45+ minutes:

Two seasons, ranking players projected to play 45+ minutes:

| Predictor | 2025/26 (tuned on) | 2024/25 (holdout) |
|---|---|---|
| Model alone | 0.229 | 0.268 |
| **Model + form blend (ships)** | **0.263** | **0.297** |
| Points per game alone | **0.324** | **0.338** |
| FPL's own published xP | 0.135 ⚠️ broken | **0.624** |
| Price | 0.088 | 0.227 |

**`FORM_BLEND` optimised at exactly 0.5 on both seasons, independently.** The
holdout was never used for tuning, so that is real evidence the blend is a
genuine effect and not fitted noise. The model also travels: it scored slightly
*better* on the season it had never seen.

Two things it does not do:

**1. It does not beat a naive points-per-game baseline.** Consistently short by
0.04–0.06 rank correlation in both seasons. Treat xP as *one input*, not an
oracle. Where the model earns its place is what a scoring average structurally
cannot see — fixture difficulty, blanks and doubles, minutes projection,
availability, and a player whose underlying numbers have not yet reached his
points total. Where a projection disagrees sharply with a player's plain scoring
record, that is a prompt to look closer, not to defer automatically.

**2. It does not beat FPL's own published xP.** An earlier version of this
document claimed it beat it by roughly double. That was wrong, and worth
explaining because the mistake is instructive. The archived `xP` column is
**broken in 2025/26**: it averages 0.16x actual points for players who actually
played, so it scores terribly and made our model look strong by comparison. On
2024/25, where the column is well-formed (0.85x), FPL's xP scores **0.624
against our 0.297** — comfortably better than ours.

`backtest.py` now checks that ratio and prints a DATA QUALITY warning when a
baseline column is unusable, so the same error is not repeated. The lesson:
**a baseline you beat easily is more likely broken than beaten.**

The backtest has also caught three real bugs on first contact with data,
including an inverted defence multiplier that would have corrupted every
projection once matches were played.
