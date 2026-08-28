# GW2 — plan

_Deadline Sat 29 Aug 03:30 AEST · planned Fri 28 Aug 22:12 AEST_

`gw2-decision.json` alongside this file holds the numbers — squad, xP,
baseline, transfer gain. **This file is for what the numbers cannot record: why.**

## Decision

## GW2 — Punk Records FC
**PROVISIONAL — do not act yet**
**Deadline** Sat 29 Aug 03:30 AEST · **act by** Fri 28 Aug 21:00 AEST

### Transfers (1 free, no hit)
| Out | In | Why |
|---|---|---|
| None | Roll | Best move remains Tarkowski to Guehi for +0.43 xP, below the 1.50 threshold |

### Starting XI (4-4-2)
| Pos | Player | Price | xP |
|---|---|---:|---:|
| GKP | Kelleher | £5.0 | 3.44 |
| DEF | Gabriel | £8.0 | 4.54 |
| DEF | Virgil | £6.5 | 4.36 |
| DEF | Senesi | £6.0 | 4.11 |
| DEF | Tarkowski | £6.0 | 3.72 |
| MID | B.Fernandes | £12.0 | 5.75 |
| MID | Semenyo | £8.5 | 4.44 |
| MID | Anderson | £6.4 | 4.35 |
| MID | Rice | £7.5 | 4.28 |
| FWD | Thiago | £8.0 | 4.28 |
| FWD | João Pedro | £7.6 | 4.07 |

**Captain** B.Fernandes (5.75 xP) · **Vice** Gabriel (4.54 xP)

### Bench (in order)
1. Verbruggen £4.5 — GKP
2. Beto £5.5 — FWD
3. O'Shea £4.0 — DEF
4. Hughes £4.5 — MID

### Chip
None. First-half chips are unused; Bench Boost still needs a double and must be used by GW19.

### Watching
- This is after the planned lock-session time; rerun lock workflow before acting if possible.
- Senesi minutes risk: Van de Ven and Porro are back in the Spurs squad.
- Anderson is reported fully fit after cramp; City role volatility remains.
- João Pedro's cup rest is positive for GW2 availability.
- Fixture projections are low confidence: bookmaker odds cover 20/50 horizon fixtures; the rest use preseason strength fallback.

## Why

- Rolling the free transfer banks flexibility for a better-defined move; the best modelled move is only +0.43 xP over the hold team.
- B.Fernandes is the clear captain on next-GW xP and has template-level ownership at 48.5%.
- Gabriel is vice because he is the highest non-captain xP option and plays in a different, later match.
- No chip matches the chip plan or has a quantified gain this week.

## What the optimiser proposed, and what I did differently

- Followed the optimiser recommendation to hold.
- The optimiser identified Tarkowski to Guehi as the best one-transfer squad but rejected it because +0.43 xP is inside the model error bars and below the 1.50 xP transfer threshold.
- No manual xP adjustments, locks, excludes, or assumed-minutes players were used.

## Considered and rejected

- Tarkowski £6.0 to Guehi £6.0: +0.43 xP versus holding, rejected below threshold.
- Captain alternatives: Gabriel 4.54 xP, Semenyo 4.44 xP, Virgil 4.36 xP, Anderson 4.35 xP. B.Fernandes leads by at least 1.21 xP.

## What the model could not see

- Team news scout found no FPL API news for owned players; all owned players were status `a`.
- Anderson is reportedly fully fit after cramp, but City role volatility remains a minutes risk.
- Senesi started GW1, but Van de Ven's return raises rotation risk.
- João Pedro has no fresh injury concern found; cup rest is a positive availability signal.
- B.Fernandes, Tarkowski, Beto, Verbruggen, O'Shea, and Hughes had no new actionable item found beyond FPL status/public watchlists.
- This plan was rerun after the planned lock-session time.
- Preseason fallback is still active for fixture strength where odds do not cover the horizon.

## What would make me wrong

- Senesi loses his place and Tarkowski to Guehi becomes a genuine minutes/security upgrade before the deadline.
- Late team news flags B.Fernandes, Gabriel, Anderson, João Pedro, or another starter after this plan.
- A price move blocks the preferred lock transfer path; bank is £0.0m and Anderson has already fallen to £6.4.
- The preseason fallback materially misprices the GW2 defensive fixtures.

---

## Review (fill in after the gameweek)

- **Projected vs actual:** 53.09 xP hold team -> {actual}
- **Captain:** B.Fernandes 5.75 xP -> {actual}
- **Verdict:** {noise / systematic error / good call that didn't land}
- **Anything for `priors.md`?** {only if repeatable across several gameweeks}
