# GW9 — lock

_Deadline Sat 31 Oct 2026 22:00 AEDT · locked Sat 31 Oct 2026 10:59 AEDT_

`gw9-decision.json` alongside this file holds the optimiser-selected wildcard
squad and five-week projections. This file records the GW9 lineup and why the
chip is being proposed.

## Decision

- **Transfers:** Wildcard; replace the full current squad with the optimiser-selected 15. Approved by the user.
- **Captain:** Welbeck · **Vice:** Wilson · Haaland constrained to start
- **Chip:** Wildcard; expected gain about 22 xP over five gameweeks versus the news-adjusted five-transfer route.
- **Post-entry sync:** Live FPL state confirmed the 15, XI, captain, vice and bench order; bank is £1.7m and squad value is £96.6m.

## Why

- The live squad has four free transfers but requires at least five immediate changes: João Pedro and Semenyo are out, while Dubravka, Senesi and Keane have material starting-minutes evidence against them.
- Wildcard 1 was already targeted for GW8–12 and the optimiser projects about 22 more horizon xP than using five transfers for a four-point hit.
- Welbeck leads the wildcard squad for GW9 at 3.00 xP; Wilson is second at 2.97 xP and plays in a different match.

## What the optimiser proposed, and what I did differently

- Followed the optimiser for all 15 wildcard selections after excluding Dubravka, Senesi and Keane on current minutes evidence.
- Re-optimised the selected 15 on `xp_next` for the GW9 XI and captain, with Haaland forced to start at the user's request. The draft command's displayed XI and captain optimise the five-week horizon, so they are not used as the one-week lineup.

## Considered and rejected

- Five transfers for a −4: Pope, Timber, Alderete, Wilson and Gyökeres in for Dubravka, Senesi, Keane, Semenyo and João Pedro. It trails the wildcard by about 22 horizon xP.
- Four free transfers without a hit cannot remove all five players whose availability or minutes evidence requires action.
- Haaland captain: his GW9 projection is 2.72 xP, 0.28 behind Welbeck, so Welbeck remains captain. Starting Haaland instead of Collins costs only 0.01 projected points.

## What the model could not see

- Chelsea ruled João Pedro out for a few weeks and Manchester City reported Semenyo unavailable; the cached API flags did not fully reflect both reports before projection.
- Dubravka was reserve goalkeeper in Tottenham's latest league lineup, Senesi was recently a substitute, and Keane faces Branthwaite's expected return.
- Bookmaker odds cover only 21 of 50 horizon fixtures; the remainder use the low-confidence `strength_overall` fallback.
- The projection model has not beaten its points-per-game baseline, so xP is treated as an input rather than certainty.

## What would make me wrong

- Dubravka, Senesi and Keane all regain secure starts immediately, or the low-ownership wildcard core loses minutes while the sold template players return sooner than reported.
- The low-ownership core loses minutes while the sold template players return sooner than reported; Haaland is now protected in the XI but not captained.

---

## Review (fill in after the gameweek)

- **Projected vs actual:** 34.4 xP → {actual}
- **Captain:** 3.00 xP → {actual}
- **Verdict:** {noise / systematic error / good call that didn't land}
- **Anything for `priors.md`?** {only if repeatable across several gameweeks}
