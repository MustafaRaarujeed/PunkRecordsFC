# Decision rules

Risk posture for this team is **balanced**: own most of the high-ownership
core, carry two or three deliberate differentials, avoid variance for its own
sake. Where a rule below has a number, use the number — these exist precisely
because they are the decisions that get made badly on instinct.

## Transfers

**Take a −4 only if the projected gain over the horizon exceeds 6.0 points**
(the 4-point cost plus a 2.0 buffer).

The buffer is not timidity. Projections carry error, and a hit is a certain loss
against an uncertain gain. In practice most hits are negative expected value,
and the ones that feel most compelling — chasing last week's returns — are the
worst. Never take a hit to chase points already scored.

Take a hit without hesitation for: an injured or suspended player who cannot be
benched, or a squad so broken that doing nothing costs more than 4.

**Never take more than one hit (−8) in a gameweek.** If the squad needs that
much surgery, it needs a wildcard.

### Banking free transfers

Free transfers bank up to 5, but the value curve flattens fast:

- Banking to **2** is usually right — it buys flexibility for a fitness test or
  a price rise without giving up much
- Banking to **3** is defensible before a known wildcard or a fixture swing
- Banking to **4 or 5** is almost always a mistake. You are sitting on unused
  value while your squad decays

Rolling a transfer when there is nothing to buy is fine and correct. Making a
transfer purely because you have one is not.

### Price changes

Prices move overnight. A player rising 0.1 is worth roughly nothing in isolation
— never take a hit or make a bad transfer to catch a rise. It matters only
cumulatively, as team value that eventually funds an upgrade.

Selling price is purchase price plus **half** the rise, rounded down. Use
`selling_price` from `state/squad.json`; `now_cost` will overstate what you get.

## Captaincy

Captaincy is the single highest-variance decision each week — more swing than
any transfer.

Present the **top three**, ranked by next-gameweek xP, each with:

- projected points and ownership
- whether it is the template pick or a differential
- the effective-ownership consequence in one line

Default to the highest xP. Deviate only when the gap is under ~0.5 points and
there is a clear reason (fixture, rotation risk, a genuine differential play
when chasing in a mini-league).

Vice-captain matters more than people think: pick someone playing in a
*different match*, ideally later, so an early blank still leaves you covered.

## Chips

Chips are worth 15–30 points each when played well and near zero when
improvised. They are governed by `state/chip-plan.md`, revised deliberately —
never decided in the last hour before a deadline.

**Each chip is available twice, once per half. First-half chips are lost at
GW19.** An unused Bench Boost in GW19 is 15 points thrown away.

| Chip | Play it when |
|---|---|
| Wildcard | The squad needs 4+ changes, or a fixture swing makes half the team wrong. Not for a single injury |
| Free Hit | A blank or double gameweek where your squad is badly exposed. Best held for a known DGW |
| Bench Boost | A double gameweek with all 15 playing twice, and a bench that is actually worth boosting |
| Triple Captain | A premium with a double gameweek, or a standout single fixture. Not on a hunch |

Before playing any chip, state explicitly what you expect it to gain versus not
playing it. If you cannot put a number on it, do not play it.

## Draft heuristics (GW1 only)

The optimiser handles the constrained maximisation. These are the things it
cannot see:

1. **Review every `no_history=1` player by hand.** Promoted-club players and new
   signings project near zero and will never be selected. Some are genuinely
   good and cheap. This is where the optimiser is reliably wrong.
2. **Minutes certainty beats upside at the cheap end.** A £4.5m defender who
   starts every week beats a £4.5m defender who might. Bench fodder that never
   plays is fine — bench fodder you are forced to *start* is a disaster.
3. **Check `penalties_order`.** A first-choice penalty taker is worth roughly
   0.3–0.5 points per game that the model does not see for new takers.
4. **Check set-piece takers** via `corners_and_indirect_freekicks_order` and
   `direct_freekicks_order` — a real and under-priced assist source.
5. **Do not over-optimise for GW1.** You get a free wildcard from GW2. A squad
   that is 95% right and flexible beats one that is 100% right and locked.
6. **Structure over individuals.** Decide the shape first (how many premiums,
   where the money goes), then let the optimiser fill it.

## What to do when the model and your judgement disagree

Adjust the input and rerun. `--lock`, `--exclude`, or a documented xP adjustment
capped at ±15%. Never hand-edit the optimiser's output — an unexplained swap is
indistinguishable from a hallucination, both to the user and to you next week.

Write the disagreement and its outcome into `state/log/gw{N}.md`. Over a season
that log tells you whether your overrides are worth anything. Most people's are
not, and the only way to find out is to have written them down.
