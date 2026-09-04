# GW3 — lock

_Deadline Sat 05 Sep 2026 03:30 AEST · acted Sat 05 Sep 2026 00:15 AEST_

`gw3-decision.json` alongside this file holds the numbers — squad, xP,
baseline, transfer gain. **This file is for what the numbers cannot record: why.**

## Decision

## GW3 — Punk Records FC
**Deadline** Sat 05 Sep 03:30 AEST · **act by** Fri 04 Sep 21:00 AEST

### Transfers (2 free, no hit)
| Out | In | Why |
|---|---|---|
| Rice £7.5 | Enzo £6.9 | Solver needs Beto fixed and prefers Enzo's 4.9 GW3 xP; also frees £0.6m |
| Beto £5.4 | Welbeck £5.9 | Beto is unavailable after joining Fiorentina; Welbeck is the solver's affordable forward replacement |

### Starting XI (4-4-2)
| Pos | Player | Price | xP |
|---|---|---:|---:|
| GKP | Kelleher | £5.0 | 3.3 |
| DEF | Senesi | £5.9 | 4.1 |
| DEF | Gabriel | £8.0 | 3.9 |
| DEF | Virgil | £6.5 | 3.8 |
| DEF | Tarkowski | £6.0 | 3.3 |
| MID | Enzo | £6.9 | 4.9 |
| MID | B.Fernandes | £12.0 | 4.9 |
| MID | Semenyo | £8.5 | 4.5 |
| MID | Anderson | £6.4 | 4.2 |
| FWD | Thiago | £8.0 | 4.2 |
| FWD | João Pedro | £7.7 | 3.4 |

**Captain** Enzo (4.9 xP) · **Vice** B.Fernandes (4.9 xP)

### Bench (in order)
1. Verbruggen £4.5 — GKP
2. Welbeck £5.9 — FWD
3. O'Shea £4.0 — DEF
4. Hughes £4.5 — MID

### Chip
None. Chip plan holds first-half chips for later fixture swings/doubles; Bench Boost must be used by GW19.

### If team news changes
- **Enzo not in the Man City squad** -> do not execute the Rice -> Enzo move without rerunning the optimiser.
- **Welbeck unexpectedly ruled out** -> do not execute the Beto replacement without rerunning the optimiser.
- **B.Fernandes absent from confirmed/credible late team news** -> captain Enzo remains; vice should be the highest available starter from the rerun.

Low confidence note: `project.py` reports preseason strength fallback, with bookmaker odds covering 20/50 projected fixtures, so fixture difficulty is still coarse outside the priced matches.

## Why

- Beto has `avail=0` and FPL news says he has joined Fiorentina permanently, so keeping him makes both the hold baseline and current-squad XI infeasible.
- The optimiser chose to use both free transfers, with no hit, to remove Beto and fund the preferred replacement structure.
- Enzo is the top GW3 xP starter in the solved XI at 4.934, narrowly ahead of B.Fernandes at 4.861.
- Vice goes to B.Fernandes because he is the next-best xP option and plays in a different match from Enzo.
- No chip: nothing in the chip plan supports forcing a GW3 chip.

## What the optimiser proposed, and what I did differently

- Followed the optimiser's move-case squad and XI.
- The normal `optimise.py --transfer --max-transfers 2` command was infeasible because its no-transfer baseline must keep unavailable Beto. I used the same `build()` ILP path for the transfer move case and recorded this in `gw3-decision.json`.
- No player was hand-swapped after the optimiser result.

## Considered and rejected

- Holding transfers was rejected because Beto is unavailable, making the current squad impossible to optimise legally.
- A one-transfer Beto-only fix was not used; with 2 free transfers and £0.0m bank, the solver found the Rice -> Enzo move was part of the best legal repair.
- B.Fernandes captain was rejected by 0.073 xP versus Enzo.

## What the model could not see

- Scout check found Beto permanently moved to Fiorentina; this matches the live FPL availability/news field.
- Scout check found no downgrade for owned Will Hughes; the injured Hughes in live material is Charlie Hughes, not this squad's Crystal Palace midfielder.
- Scout check found no current injury downgrade for Kelleher, Senesi, Gabriel, Virgil, Tarkowski, Anderson, B.Fernandes, Rice, Semenyo, João Pedro, Thiago, Verbruggen, O'Shea or Hughes.
- Man City midfield carries rotation uncertainty after new arrivals, but scout findings did not justify reducing Anderson/Semenyo; Enzo is a new-club player whose minutes history comes from his old club.
- The projection run warns that 271 players have too little history to model and 53 lack element-summary history.

## What would make me wrong

- Enzo missing the squad or starting from the bench would undermine both the transfer and captaincy.
- Welbeck not being available would make the Beto repair bad.
- A late Man City rotation leak affecting Enzo, Semenyo or Anderson would require a rerun.
- The preseason strength fallback being badly wrong for GW3 fixtures could distort several close xP calls.

---

## Review (fill in after the gameweek)

- **Projected vs actual:** 49.3 xP -> {actual}
- **Captain:** 4.934 xP -> {actual}
- **Verdict:** {noise / systematic error / good call that didn't land}
- **Anything for `priors.md`?** {only if repeatable across several gameweeks}
