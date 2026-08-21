# GW1 - lock

_Deadline Sat 22 Aug 03:30 AEST . acted Fri 21 Aug 22:09 AEST_

`gw1-decision.json` alongside this file holds the numbers - squad, xP,
baseline, transfer gain. This file is for what the numbers cannot record: why.

## Decision

- **Squad action:** transfer mode refused before GW1, so replace the saved auto-pick squad with the final optimiser draft.
- **Captain:** B.Fernandes. **Vice:** Gabriel.
- **Chip:** none.

## Why

- The optimiser selected the best legal GW1-5 draft from forced-refreshed FPL core data, refreshed element-summary history, and current odds coverage.
- Transfer planning is invalid before the first deadline because squad changes are unlimited and free.
- The draft spends the full 100.0m; prices were refreshed at lock and there is no bank.

## What the optimiser proposed, and what I did differently

- Did not hand-edit the squad. Reran the optimiser with `--exclude Dubravka --exclude Kusi-Asare --exclude Scarlett --exclude Neave --exclude Guehi --lock Beto`.
- Exclusions came from lock team-news review: Dubravka was not predicted to start, Kusi-Asare was not predicted to start, Scarlett/Neave were zero-history replacement bench forwards, and Guehi had tactical start risk.
- Did not use `--allow-assumed`; `data/projections.csv` had no asserted-minutes players to audit.

## Considered and rejected

- Raw optimiser draft scored 291.2 XI xP with B.Fernandes doubled but contained Dubravka, Guehi and a no-history 4.5m forward. The final constrained draft scores 288.4 XI xP with B.Fernandes doubled.
- The current synced squad is treated as FPL auto-pick, not as a planned starting point. Its flagged/watch players were not protected.
- Transfer-mode optimisation was rejected by the script because no gameweek has finished yet.

## What the model could not see

- Preseason fallback is still in use; bookmaker odds cover 13/50 fixtures, with the strength model used elsewhere.
- The model reports 229 players with too little history, plus 25 with stale history.
- Anderson and Senesi are selected but flagged by `project.py` as new-club players; their minutes record comes from their old clubs.
- Beto is locked as third bench because he is the first model-backed cheap forward; external lineup sources disagree on whether he starts, so this is bench cover rather than a starting claim.
- Premier Injuries reports Bruno Guimaraes as a late fitness test and Arsenal missing Saliba/Timber; Bruno G. is in the current auto-pick squad but not the optimiser draft.
- Scout review flagged Doku, Matheus N., Dovin and Enzo in the current auto-pick squad as injury/minutes risks; none are in the optimiser draft.
- FPL Joe loaded only its dynamic shell to the crawler, so it was not used for player-specific claims.

## What would make me wrong

- Anderson or Senesi is not expected to start, invalidating old-club minutes as a draft input.
- Kelleher, Anderson, Senesi or Beto loses his predicted minutes after the final public team-news pass.
- A promoted-club or new-signing player with reliable minutes is omitted because the model cannot see him without a documented minutes assumption.

---

## Review (fill in after the gameweek)

- **Projected vs actual:** 288.4 XI xP with captain doubled -> {actual}
- **Captain:** B.Fernandes 30.14 GW1-5 xP -> {actual}
- **Verdict:** {noise / systematic error / good call that didn't land}
- **Anything for `priors.md`?** {only if repeatable across several gameweeks}
