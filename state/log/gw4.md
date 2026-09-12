# GW4 — lock

_Deadline Sat 12 Sep 2026 22:30 AEST · acted Sat 12 Sep 2026 21:00 AEST_

`gw4-decision.json` alongside this file holds the numbers — squad, xP,
baseline, transfer gain. **This file is for what the numbers cannot record: why.**

## Decision

## GW4 — Punk Records FC
**Deadline** Sat 12 Sep 22:30 AEST · **act by** Sat 12 Sep 21:00 AEST

### Transfers (1 free, no hit)
| Out | In | Why |
|---|---|---|
| None | Roll | Best move is Verbruggen to Dubravka for +0.43 xP, below the 1.50 threshold |

### Starting XI (3-4-3)
| Pos | Player | Price | xP |
|---|---|---:|---:|
| GKP | Kelleher | £5.0 | 2.8 |
| DEF | Senesi | £5.9 | 4.3 |
| DEF | Gabriel | £8.0 | 3.6 |
| DEF | Virgil | £6.5 | 3.4 |
| MID | B.Fernandes | £12.0 | 4.2 |
| MID | Enzo | £6.9 | 3.9 |
| MID | Semenyo | £8.4 | 3.5 |
| MID | Anderson | £6.3 | 3.4 |
| FWD | Welbeck | £5.9 | 3.7 |
| FWD | João Pedro | £7.7 | 3.6 |
| FWD | Thiago | £7.9 | 3.5 |

**Captain** Senesi (4.3 xP) · **Vice** B.Fernandes (4.2 xP)

### Bench (in order)
1. Verbruggen £4.5 — GKP
2. Tarkowski £6.0 — DEF
3. O'Shea £4.0 — DEF
4. Hughes £4.5 — MID

### Chip
None. First-half chips are unused; Bench Boost still needs a double and must be used by GW19.

### If team news changes
- **Senesi absent from credible late team news** -> captain B.Fernandes; start Tarkowski for Senesi if there is no rerun.
- **B.Fernandes rested or ruled out** -> vice Enzo.
- **Kelleher unexpectedly benched** -> start Verbruggen.
- Fixture projections are low confidence: bookmaker odds cover 10/50 horizon fixtures; the rest use preseason strength fallback.

## Why

- Rolling the free transfer banks flexibility; the best modelled move is only +0.43 xP over the hold team.
- Senesi is the top next-GW xP option at 4.3, narrowly ahead of B.Fernandes at 4.2.
- B.Fernandes is vice because he is the next-best captain option and plays in a later match than Senesi.
- No chip matches the chip plan or has a quantified gain this week.

## What the optimiser proposed, and what I did differently

- Followed the optimiser recommendation to hold.
- The optimiser identified Verbruggen to Dubravka as the best one-transfer squad but rejected it because +0.43 xP is inside the model error bars and below the 1.50 xP transfer threshold.
- Reran with `--max-transfers 0` so `gw4-decision.json` records the issued hold team.
- No manual xP adjustments, locks, excludes, or assumed-minutes players were used.

## Considered and rejected

- Verbruggen £4.5 to Dubravka £4.0: +0.43 xP versus holding, rejected below threshold.
- Captain alternatives: B.Fernandes 4.2 xP and Enzo 3.9 xP. Senesi leads by 0.1 xP and 0.4 xP respectively.

## What the model could not see

- Scout found no direct injury flag for Senesi, Gabriel, Virgil, Kelleher, Thiago, João Pedro, Tarkowski or Verbruggen.
- B.Fernandes played 90 Thursday and took a knock, but scout found no reported concern; still a mild load/rotation risk before the derby.
- Brentford are missing Nathan Collins, slightly worsening Kelleher's defensive context.
- FPL official cache has no `news` text for the owned squad after the fresh sync; Welbeck and Anderson are explicitly 100% available.
- The projection run warns that 257 players have too little history to model and 15 lack element-summary history.
- Preseason fallback is still active for fixture strength where odds do not cover the horizon.

## What would make me wrong

- Senesi rotation or a Spurs defensive reshuffle would make the captaincy too aggressive.
- B.Fernandes being rested after the Thursday 90 would weaken both the XI and vice-captain choice.
- Brentford defensive injuries turning Bournemouth away into a poor keeper spot would make starting Kelleher over Verbruggen too thin.
- Dubravka outscoring Verbruggen by several points would make rolling the transfer look conservative, but the pre-deadline gain was too small to justify action.

---

## Review (fill in after the gameweek)

- **Projected vs actual:** 44.2 xP -> {actual}
- **Captain:** Senesi 4.3 xP -> {actual}
- **Verdict:** {noise / systematic error / good call that didn't land}
- **Anything for `priors.md`?** {only if repeatable across several gameweeks}
