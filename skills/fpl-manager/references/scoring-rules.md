# 2026/27 scoring — verified

Every value here was read from `bootstrap-static` → `game_config.scoring` on
2026-08-07, not from memory. `scripts/validate.py --rules` asserts them against
the live API on every run, so if the Premier League changes something
mid-season you get a loud failure rather than weeks of quietly wrong numbers.

## Points

| Event | GKP | DEF | MID | FWD |
|---|---|---|---|---|
| Goal | 10 | 6 | 5 | 4 |
| Assist | 3 | 3 | 3 | 3 |
| Clean sheet (60+ mins) | 4 | 4 | 1 | 0 |
| Every 2 goals conceded | −1 | −1 | 0 | 0 |
| Defensive contribution | — | +2 | +2 | +2 |
| Playing 1–59 mins | +1 | +1 | +1 | +1 |
| Playing 60+ mins | +2 | +2 | +2 | +2 |
| Every 3 saves | +1 | — | — | — |
| Penalty save | +5 | — | — | — |
| Penalty miss | −2 | −2 | −2 | −2 |
| Yellow card | −1 | −1 | −1 | −1 |
| Red card | −3 | −3 | −3 | −3 |
| Own goal | −2 | −2 | −2 | −2 |
| Bonus | 1–3 | 1–3 | 1–3 | 1–3 |

## Defensive contribution (DefCon)

Worth **+2, at most once per match**, at these thresholds:

| Position | Threshold | Counts |
|---|---|---|
| DEF | **10** | clearances + blocks + interceptions + tackles (CBIT) |
| MID, FWD | **12** | CBIT + ball recoveries (CBIRT) |
| GKP | not eligible | — |

**Verified against 2025/26 season totals**, since the API field name is
ambiguous. `defensive_contribution` is a **raw action count**, not a count of
times the threshold was hit, and `clearances_blocks_interceptions` **excludes**
tackles despite its name:

- Senesi (DEF): CBI 357 + tackles 62 = 419 = `defensive_contribution` ✓
- Anderson (MID): CBI 106 + tackles 103 + recoveries 306 = 515 ✓

This matters: the model needs P(actions ≥ threshold) per match via Poisson, not
a season average. See `projection-model.md`.

Forwards have been eligible since 2025/26 — this is **not** a new rule. In
practice no forward finished in the top ten DefCon scorers last season, so treat
forward DefCon as a rounding error, not a strategy.

## 2026/27 rule change

The BPS penalty for being dispossessed in a tackle was **removed**. This
quietly helps dribbling wingers and attacking full-backs, who were previously
punished for taking players on. Expect their bonus-point returns to rise
relative to last season's data — the model uses last season's bonus rates, so
it will *understate* these players early on.

## Squad and transfers

- 15 players: 2 GKP, 5 DEF, 5 MID, 3 FWD
- £100.0m budget, max 3 players per club
- Starting XI: 1 GKP, 3–5 DEF, 2–5 MID, 1–3 FWD
- Free transfers bank up to **5** (`max_extra_free_transfers` = 4)
- Extra transfers cost **−4** each
- Selling price = purchase price + half the rise, rounded down. You do not get
  the full profit, so `now_cost` is the wrong number for sales — use
  `selling_price` from `state/squad.json`.

## Chips

Each chip is available **twice**, once per half of the season:

| Chip | First half | Second half |
|---|---|---|
| Wildcard | GW2–19 | GW20–38 |
| Free Hit | GW2–19 | GW20–38 |
| Bench Boost | GW1–19 | GW20–38 |
| Triple Captain | GW1–19 | GW20–38 |

Unused first-half chips are **lost** at GW19 — they do not roll over. Only one
chip may be played per gameweek.
