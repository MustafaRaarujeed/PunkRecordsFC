# Learned priors

Model adjustments that survived contact with reality. One line each, with the
evidence that justifies it.

**The bar is repeatability, not a bad week.** A captain blanking is noise. A
defender consistently under-projected on DefCon across five gameweeks is signal.
If you cannot point to several gameweeks of evidence, it does not go in here.

Resist rewriting the model after one bad result. That is how a model gets
overfitted to last Saturday.

## Known model weaknesses (from construction, not yet from evidence)

These are documented in `references/projection-model.md` and are starting
hypotheses, not findings:

- `no_history=1` players project near zero — promoted clubs and new signings are
  invisible to the model and need manual review every draft
- The DefCon dispersion constant (0.90) is a guess and has never been backtested
- Bonus is likely understated for dribbling wingers and attacking full-backs,
  because the 2026/27 BPS change removed the dispossessed-in-a-tackle penalty
  but the model trains on 2025/26 bonus rates
- New penalty takers are invisible — xG only reflects penalties actually taken
  last season

## Findings

| Date | Finding | Evidence | Adjustment |
|---|---|---|---|
| — | none yet | — | — |
