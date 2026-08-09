# The instruction card

The user is executing this by hand on the FPL website, often late at night
before an overnight deadline. Optimise for *acting*, not for reading.

Rules: exact names and prices, no hedging on the action, reasoning compressed to
one line per decision. If you need to explain more, put it after the card.

## Lock card

```markdown
## GW{N} — Punk Records FC
**Deadline** Sat 22 Aug 03:30 AEST · **act by** Fri 21 Aug 21:00 AEST

### Transfers (1 free, no hit)
| Out | In | Why |
|---|---|---|
| Watkins £9.0 | Isak £10.5 | +4.2 xP over 5 GWs, Watkins' fixtures turn hard |

### Starting XI (3-4-3)
| Pos | Player | Price | xP |
|---|---|---|---|
| GKP | Raya | £5.5 | 4.1 |
| DEF | ... | | |

**Captain** Haaland (7.8 xP) · **Vice** Saka (5.9 xP)

### Bench (in order)
1. Sels £5.0 — GKP
2. ...

### Chip
None. Bench Boost still held for a GW-double; must be used by GW19.

### If team news changes
- **Isak not in the squad Friday** → buy Ekitiké £8.5 instead, same transfer
- **Haaland fails his fitness test** → captain Saka, bring in Wood
```

## Plan card

Same shape, but the header says **PROVISIONAL — do not act yet**, and it ends
with what you are waiting on:

```markdown
### Watching
- Isak fitness — Newcastle presser Thu ~22:00 AEST
- Gabriel price rise — 0.1 away, would cost us 0.1 of team value
```

## Rules for the card

- **Prices** always to one decimal with the £ sign. State them as of when you
  fetched, and refetch at lock — they move overnight.
- **Bench order matters.** Number it. Position 1 comes on first.
- **Never write "consider" or "you might want to".** Give the decision. Put
  genuine uncertainty in the contingency section, where it is actionable.
- **One line of reasoning per transfer.** The full analysis goes in
  `state/log/gw{N}.md`, not in the card.
- **Always state the chip line**, even when it is "none" — an unplayed chip
  expiring at GW19 is a silent loss, and the card is where it gets caught.
- **Flag low confidence explicitly.** If `project.py` reported the preseason
  strength fallback, or you could not get team news, say so in one line. Do not
  present a coarse projection with the same certainty as a sharp one.
- **Sydney time only.** Give the real deadline and the act-by time. Never quote
  a bare UTC time.

## After the card

Write `state/log/gw{N}.md`:

- the card as issued
- what the optimiser proposed and what you overrode, with reasons
- transfers considered and rejected, with the xP gap
- anything the model could not see (role change, rotation, a manager's comment)
- what would make you wrong

Next season's edge is in this file. Write it as if someone else has to audit it.
