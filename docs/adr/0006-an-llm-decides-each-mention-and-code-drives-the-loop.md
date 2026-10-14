# 6. An LLM decides each mention, and code drives the loop

**Status:** accepted

## The decision

For PER, ORG and LOC, code walks a class's mentions in reading order. The
first opens an entity; for every later one, an LLM makes one choice: an
entity so far, or a new one. The reply is constrained by a JSON schema to
exactly those choices. Equal strings are asked about too. EMAIL, PHONE,
URL, DATE and ATTACHMENT are grouped by exact match after normalising.
A rule-only grouper is kept as the baseline.
(`group-entities/`, `scripts/group.py`)

## Why a decision per mention rather than one answer per message

Asking for a whole grouping as one JSON answer needs validation after the
fact — every span used exactly once, no invented ids, no mixed classes —
and a retry when it fails. Driving the loop from code makes all of that
true by construction: every mention is asked about once, and the model
can only name a choice it was offered. Each decision is also small enough
for a local model, and its stated reason is kept for review.

## Why equal strings are asked about

Two people can share a first name; "the Committee" can mean two
committees. Merging every repeated string by rule was the first design,
and was rejected for exactly that reason: it is the case a rule cannot
get right and the model can. An email address or a phone number, on the
other hand, is its own identity, so exact match decides there.

## Why keep the rules

The rules (exact match, plus one name's words containing another's) are
cheap and transparent, and the LLM has to beat them to be worth running.
On 100 judged messages, 66 had something to decide: the LLM grouped 62
right (94%), the rules 44 (67%). The rules miss abbreviations and
initials, and merge on shared words ("Congress" with a campaign named
"… for Congress"); the LLM's errors are all over-merges of related
things.

## Consequences

- About 3.75 decisions per message on the selected set; a quarter of
  messages need none.
- A message whose reply can't be parsed twice is dropped, like a veto.
- Decisions are cached on the text, the mention, the entities offered,
  the prompt version and the model, so a rerun costs nothing and a prompt
  change redoes only what it touches.
