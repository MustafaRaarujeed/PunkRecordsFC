# GW5 — lock

_Deadline Sat 19 Sep 03:30 AEST · acted Fri 18 Sep 22:14 AEST_

`gw5-decision.json` alongside this file holds the numbers — squad, xP,
baseline, transfer gain. **This file is for what the numbers cannot record: why.**

## Decision

## GW5 — Punk Records FC
**Deadline** Sat 19 Sep 03:30 AEST · **act by** Fri 18 Sep 21:00 AEST

### Transfers (2 free, no hit)
| Out | In | Why |
|---|---|---|
| Kelleher £5.0 | Dubravka £4.0 | Part of optimiser move worth +1.65 xP over 5 GWs, also releases £1.0m |
| O'Shea £4.0 | Keane £4.8 | Upgrades a low-projection defender within budget |

### Starting XI (4-4-2)
| Pos | Player | Price | xP |
|---|---|---:|---:|
| GKP | Dubravka | £4.0 | 3.17 |
| DEF | Senesi | £5.8 | 4.27 |
| DEF | Keane | £4.8 | 3.57 |
| DEF | Gabriel | £8.0 | 3.10 |
| DEF | Tarkowski | £6.1 | 2.89 |
| MID | B.Fernandes | £12.0 | 3.90 |
| MID | Enzo | £6.9 | 3.85 |
| MID | Semenyo | £8.4 | 3.31 |
| MID | Anderson | £6.3 | 3.06 |
| FWD | Welbeck | £5.9 | 3.28 |
| FWD | Thiago | £7.8 | 3.19 |

**Captain** B.Fernandes (3.90 xP) · **Vice** Enzo (3.85 xP)

### Bench (in order)
1. Verbruggen £4.5 — GKP
2. Virgil £6.5 — DEF
3. João Pedro £7.8 — FWD
4. Hughes £4.4 — MID

### Chip
None. First-half chips still held; Bench Boost needs a double and must be used by GW19.

### If team news changes
- **João Pedro ruled out before deadline** → no action unless you cannot field XI; he is already benched.
- **Late City news hits Enzo, Semenyo, or Anderson** → start Virgil first, then João Pedro only if still likely to feature.
- **Senesi not expected to start** → keep the transfers, do not captain him; Virgil is first outfield bench cover.

Low confidence note: projections still use preseason team-strength fallback where bookmaker odds do not cover the fixture; odds cover 20/50 horizon fixtures.

## Why

- Used both free transfers because the optimiser found +1.65 xP over holding, just above the 1.50 no-hit threshold.
- Took Dubravka over Kelleher because the move improves the XI and frees budget while keeping a legal squad.
- Took Keane over O'Shea because O'Shea was the weakest outfield squad projection and Keane fits the freed budget.
- Captained B.Fernandes instead of optimiser-captain Senesi because Senesi has scout-reported role/start risk and the next-GW xP gap is only 0.36.
- Vice-captained Enzo as the next-best xP option in a different match from B.Fernandes.
- No chip because the chip plan holds first-half chips for wildcard timing, blanks, doubles, or a premium double.

## What the optimiser proposed, and what I did differently

- Followed the optimiser on transfers, XI, and bench order.
- Overrode captaincy from Senesi to B.Fernandes. This follows the captaincy rule allowing deviation when the gap is under ~0.5 xP and there is a clear rotation/minutes reason.

## Considered and rejected

- Rolling both transfers: rejected because holding projected 40.20 xP versus 41.86 xP after two free transfers.
- Captaining Senesi: rejected despite 4.27 xP because the scout report says he started midweek and may not be nailed in the recent league pairing.
- Starting João Pedro: rejected because the FPL API flags him at 75% and the scout report says Chelsea will make a late decision after final training.

## What the model could not see

- João Pedro withdrew from Brazil duty, missed Tuesday training, and remains a late Chelsea fitness decision.
- Senesi has no FPL injury flag, but his starting role is uncertain after a midweek start and recent league pairing uncertainty.
- Manchester City press-conference information was incomplete at the time of the scout report; City-owned midfield minutes carry extra uncertainty.
- Arsenal defensive clean-sheet inputs may be slightly optimistic if the model does not account for Saliba remaining out.
- Fixture difficulty is still partly low confidence: bookmaker odds cover 20 of 50 horizon fixtures and the rest use preseason strength fallback.

## What would make me wrong

- Senesi starts and returns strongly while B.Fernandes blanks; the captain override would have cost points.
- Dubravka loses the Spurs goalkeeping spot or Kelleher outscores him materially over the next five gameweeks.
- João Pedro is fully fit and starts, making the bench order too conservative.
- City press-conference news later reveals a likely benching for one of Enzo, Semenyo, or Anderson.

---

## Review (fill in after the gameweek)

- **Projected vs actual:** 41.86 → {actual}
- **Captain:** 3.90 → {actual}
- **Verdict:** {noise / systematic error / good call that didn't land}
- **Anything for `priors.md`?** {only if repeatable across several gameweeks}
