# 11. Every grouped message is judged, and who judged it is recorded

**Status:** accepted

## The decision

Each message grouped for the fine-tuning set is read as it will be
trained on and given a verdict: keep, drop for a grouping error, or drop
for a leak, with the reason. Verdicts are written per message
(`notes/verdicts-*.jsonl`, ignored) as well as in a readable report. The
reading so far is done by an LLM assistant (Claude), and the numbers it
produced are reported as its verdicts until they are checked against a
person's.

## Why read everything

The agreement filter ([ADR 8](0008-grouping-errors-are-caught-by-checking-outputs.md))
only knows where two groupers differ; it says nothing about a merge both
make, or a name neither detector found. Reading every message catches
both, and settles the disagreements as it goes, so judged-right hard
cases stay in the set rather than being dropped with the wrong ones.

## Why record the judge

An LLM judging an LLM is a reasonable first pass and a weak final word.
A sample of messages grouped by hand (`group.py --review`, then
`--score`) is what turns these numbers into measured ones, and says
whether the judge was lenient.

## Consequences

- Over 180 judged messages the grouping model was right on 94% of those
  with something to decide, consistent across two samples.
- Leaks found while reading are mostly repeats of one string — a mailing
  list's name in a standard footer — which points at the fix: mask a
  string everywhere once it is detected anywhere, rather than dropping
  each message.
