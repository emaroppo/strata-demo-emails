# 4. Numbers are dev numbers until a gold set exists

**Status:** accepted

## The decision

Until a random, double-checked gold set exists (`docs/roadmap.md`), model
comparisons are reported on an interim dev set — the 29 validation
messages of dataset version 7 — and every such number is labelled
"dev (29, non-random)". The leak rate of the masked output is bounded by
reading a random sample by hand instead.

## Why

Those 29 messages are not random, they were used to choose settings, and
29 is few. A number that looks like a held-out result and isn't is worse
than no number. But waiting for the gold set would have stopped every
comparison, so the comparisons run, and say what they are.

The leak rate is different: it can be measured honestly now, by reading.
100 kept messages drawn at random, read against the guide, bound the
rate for the whole kept set: none found in 100 means fewer than about 3%
at 95% confidence.

## Consequences

- The README's results table carries the label, and the learning curves
  are on the same set.
- The hand audit found no identifying leaks in 100; read strictly
  against the guide, three minor ones (a title outside a name, a mailing
  list's name, a platform's name).
- Grouping is measured separately
  ([ADR 11](0011-every-grouped-message-is-judged.md)).
