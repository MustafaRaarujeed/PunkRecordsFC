# The projection model

Full plain-language explanation, including a glossary of every statistic and
constant: `{{PROJECT_ROOT}}/docs/model-explained.md`. Read that when the user
asks why a number is what it is.

`scripts/project.py` produces one number per player per gameweek: expected
points. Read this before defending a projection to the user, and *definitely*
before overriding one.

## Why a model at all

An LLM asked to rank footballers produces a ranking that is plausible, stable
under rephrasing, and unrelated to the evidence. It cannot show its working, and
it silently smuggles in stale training data. The model exists so that every
recommendation traces back to a number that traces back to a fetched file.

Your judgement is still essential — it just enters at defined points (adjusting
inputs, catching what the data cannot see), not by quietly reordering the output.

## Pipeline

```
history_past / current season  ->  per-90 rates
team strength                  ->  expected goals per fixture
rates x minutes x fixture      ->  xP per gameweek
```

### 1. Source season

Preseason, every current-season field is zero, so the model reads the most
recent `history_past` entry from `element-summary`. In-season it blends, with
current-season weight `min(1, minutes / 900)` — roughly ten full matches before
this season fully displaces last.

Reported per player in the `source` column: `history:2025/26`, `blend:0.62`,
`current`, or `none`.

### 2. Minutes

Minutes dominate everything. A brilliant player who plays 45 minutes beats
nobody.

- `p_start` = starts ÷ 38, scaled by availability
- `xmins` = total minutes ÷ 38, scaled by availability
- availability: status `a` → 1.0 (or `chance_of_playing_next_round` ÷ 100),
  `d` → the stated chance or 0.5, and `i`/`s`/`u`/`n` → 0

Players with availability 0 are excluded from the optimiser outright.

### 3. Expected goals per fixture

```
xG(home) = 1.42 x 1.10 x attack(home) x defence(away)
```

Three sources, in order of preference:

1. **Bookmaker odds** (`scripts/odds.py`). Where a fixture is priced, its
   expected goals replace the calculation entirely. Bookmakers price matches
   better than anything we can build, so this is not blended — it wins outright.
   Odds typically cover only 1–2 gameweeks ahead.
2. `strength_attack_*` / `strength_defence_*`, once matches have been played.
3. The 1–5 `strength_overall_*` ratings via `1 ± 0.35 x (s − 3) / 2`. Coarse,
   and the only option in preseason.

`project.py` reports which sources were used and how many fixtures the odds
covered. When coverage is partial, do not present the whole horizon at one
confidence level.

Odds are inverted to expected goals by de-vigging the 1X2 prices, recovering
total goals from the over/under line under a Poisson total, then solving for the
supremacy that reproduces the home win probability.

### 4. Fixture adjustment is relative to the team baseline

A player's historical xG/90 already embeds their team's usual output. Adjusting
by league-average expected goals would count team quality twice — City players
would get credit for being City players once in their own rates and again in
the fixture multiplier.

So the multiplier is `xG(this fixture) ÷ xG(that team's average fixture)`,
isolating the fixture effect. This is what `baseline_goals()` computes.

### 5. Points

- Appearance: `2 x p_start + 1 x (p_appear − p_start)`
- Goals: `xG90 x mins_share x fixture_mult x goal_points[pos]`
- Assists: `xA90 x mins_share x fixture_mult x 3`
- Clean sheet: `exp(−xG_against) x cs_points[pos] x p_start` — needs 60 minutes,
  hence `p_start` not `p_appear`
- Goals conceded: exact `E[−floor(conceded ÷ 2)]` under Poisson, not the −0.5 ×
  xGA approximation
- **DefCon**: `P(actions ≥ threshold) x 0.90 x 2` where actions ~ Poisson(dc90 ×
  mins_share). The 0.90 is a dispersion correction — real defensive-action
  counts are overdispersed relative to Poisson, so the raw calculation
  overstates the probability for players sitting just above the threshold
- Bonus: last season's bonus per 90, scaled by minutes
- Cards: yellow per 90, scaled by minutes

Doubles and blanks fall out for free: the model sums over every fixture a team
has in that gameweek, so a blank scores zero and a double scores twice.

## What the backtest actually found

Replayed over 2025/26 GW6–38 with no lookahead (`scripts/backtest.py`), scored
on rank correlation against actual points. "Decision-relevant" means players
projected to play 45+ minutes — the ones we would consider owning.

Validated on two seasons: 2025/26 (which the constants were tuned on) and
2024/25 as an untouched holdout.

| Predictor | 2025/26 | 2024/25 holdout |
|---|---|---|
| Structural model alone | 0.229 | 0.268 |
| **Blended with points-per-game** | **0.263** | **0.297** |
| Points per game alone | **0.324** | **0.338** |
| FPL's own published xP | 0.135 (broken column) | **0.624** |
| Price | 0.088 | 0.227 |

Read that table honestly. **A naive "points per appearance" baseline ranks
decision-relevant players better than this model does, in both seasons**, and
FPL's own xP is far better again on the season where it is measurable.
`FORM_BLEND = 0.5` beats the model alone and is what ships, but it does not beat
either baseline outright.

The one strong result: `FORM_BLEND` optimised at exactly 0.5 on the holdout too,
independently. The blend is real, not overfitting.

So: treat the xP numbers as *one input*, not an oracle. Where the model earns
its place is the things points-per-game structurally cannot see — fixture
difficulty, blanks and doubles, minutes projection, availability, and DefCon
for a player whose scoring rate has not caught up yet. Where a projection
disagrees with a player's plain scoring record, that is worth a second look
rather than automatic deference.

Other measured results:

- **Recency weighting makes it worse.** Exponentially decaying older gameweeks
  dropped rho from 0.231 to 0.187 at decay 0.9. Flat season averages win. Form,
  as usually understood, is mostly noise — now measured, not asserted.
- **The model over-predicts**, by +0.50 points on average, concentrated at the
  top: decile 10 projects 4.95 and delivers 3.89. Captaincy and hit decisions
  live in that decile, so discount the top end rather than taking it at face
  value.
- **A negative binomial for DefCon was rejected.** It improved the component's
  log-loss by 26%, but end-to-end it moved rank correlation by +0.014 while
  making bias worse. Component-level log-loss is maximised by a near-constant
  predictor that ranks players uselessly — so `DC_SHAPE` stays 0 and Poisson
  remains in use. The lesson generalises: tune against end-to-end accuracy.
- **Minutes are over-projected mid-range**: predicted 70–85 delivers 63,
  predicted 50–70 delivers 47.

### Caveat that matters

Constants were tuned on 2025/26 across many iterations. 2024/25 now serves as a
holdout and `FORM_BLEND` survived it unchanged, which is reassuring — but the
holdout **says nothing about DefCon**, because that rule did not exist in
2024/25 and the underlying stats were not even recorded. The DefCon term is
inert there. Re-run against 2026/27 once there is enough of it.

## The baseline column — use this

`projections.csv` carries the naive baseline alongside every projection, because
across both backtested seasons it out-ranks the model:

| Column | Meaning |
|---|---|
| `ppg` | Points per gameweek from observed scoring, scaled by availability |
| `ppg_horizon` | That baseline over the same fixtures as `xp_horizon` |
| `xp_edge` | `xp_horizon - ppg_horizon` — where the model departs from the record |
| `stale` | 1 if the player's last PL season is not the most recent one |

**`xp_edge` is the column to read when deciding whether to trust a projection.**
Near zero means model and record agree, so the number is well supported. A large
edge is a *claim*:

- **Strongly positive** — the model backs a player against his scoring record.
  Legitimate reasons: kind fixtures, a double gameweek, rising minutes, DefCon
  the points total has not caught up with. Check which it is.
- **Strongly negative** — the model is fading a proven scorer. Legitimate
  reasons: hard fixtures, a blank, rotation risk. Also the classic failure mode:
  missing data.

```bash
python scripts/project.py --disagree 10   # both tails, ranked
```

**Always check `stale` before acting on a large edge.** A stale player last
played the Premier League years ago, and if that was before 2025/26 there is no
defensive-contribution data at all — so `dc90` is 0 and DefCon silently scores
zero. Preseason this hits 24 players, mostly promoted clubs. Furlong and Ajayi
both show edges near −5 for exactly this reason, not for any footballing one.

## Known weaknesses — read these before trusting a number

1. **No-history players are projected near zero.** Promoted-club players and new
   signings have no Premier League record. They are flagged `no_history=1`.
   The optimiser will never pick them. **This is the model's biggest blind spot
   and it needs manual review every draft.**
2. **Fixture difficulty beyond the odds window is coarse.** See step 3. Odds
   run 1–2 gameweeks ahead; a 6-week horizon is mostly fallback ratings.
3. **Penalties are only implicit.** A player's xG includes penalties they took
   last season. A *new* penalty taker is invisible to the model. Check
   `penalties_order` in `bootstrap-static` manually.
4. **Role changes are invisible.** A defender moved to midfield, a winger moved
   central, a new manager's system — the model sees only last season's output.
5. **DefCon is miscalibrated in both directions.** Measured on 2025/26: where
   the model predicts under 10%, players actually hit 10.6%; where it predicts
   81%, they hit 54%. Defensive-action counts are overdispersed and Poisson
   cannot represent that. Treat DefCon projections near the threshold as soft,
   and distrust the very confident ones most.
6. **Bonus is understated for dribblers**, because the 2026/27 BPS change
   removed the dispossessed-in-a-tackle penalty and the model trains on last
   season's bonus rates.

## Making an adjustment

When you have a real reason to disagree, adjust the *input*, not the output:

- Use `--lock` / `--exclude` on the optimiser for a hard call
- Cap discretionary xP adjustments at **±15%** and write the justification into
  `state/log/gw{N}.md`

If you find yourself wanting a bigger adjustment than that, the model is wrong
in a way worth fixing properly — record it in `state/priors.md`.
