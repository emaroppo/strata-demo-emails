# Entity grouping and indexing

Design notes for the stage that turns detected PII spans into indexed
placeholders (`[PER_1]`, `[PER_2]`, `[ORG_1]`, …). Status: being built.

## Where it sits

```
detect (GLiNER masks, tagger vetoes)  →  group + index (this stage)  →  pseudonymise  →  SFT

fine-tuned model output (with placeholders)  →  replacement (fill placeholders)
```

Today `scripts/anonymise.py` replaces every span with its class (`[PER]`).
This stage decides which spans refer to the same entity and numbers them,
so the training data carries consistent indexed placeholders, and
replacement on the fine-tuned model's output becomes a per-email mapping
that is consistent by construction.

## Where the code lives

- In this repo, as `group-entities/` beside `prepare-email/`. It is the
  next stage of the same pipeline, so one repo tells the whole story.
- Not in strata core, and not in a second repo.
- It graduates to a `strata.models` plugin in `strata-plugins` only if a
  second use appears (that is, "an LLM assigns structure to candidate
  spans, validated in code" turns out to be generic).

## How spans are grouped

Each class is grouped on its own, so a `PER` can never share an index with
an `ORG`.

**PER, ORG and LOC: one decision per mention.** Code walks a class's
mentions in reading order. The first opens entity 1. For every later one,
a local LLM makes a single constrained choice: one of the entities so far,
shown with their mentions, or `new`. Exact repeats are asked about too,
because two equal strings are not the same entity by default: two people
called "Sam", a father and son both "Lopez", "the Committee" meaning two
committees.

**EMAIL, PHONE, URL, DATE and ATTACHMENT: exact match.** The first three
*are* their identity, so equal after normalising (case, digits only for a
phone, no scheme for a URL) means the same. DATE and ATTACHMENT are merged
on exact match as a simplification: two different "Tuesday"s in one
message are rare and harmless to merge.

The LLM only chooses. It never rewrites text, never sees an id it can
invent, and never decides the numbering: substitution and indexing happen
in code. It runs on llama.cpp (`llama-server`, OpenAI-compatible) on the
GX10.

**Index order:** by first appearance in the text, per class, computed in
code from the groups. No role inference.

## Validation

The loop assigns every mention by construction, and the choice is
constrained to the offered ids plus `new` by a JSON schema, so "every span
exactly once", "no invented ids" and "no mixed classes" hold without being
checked after the fact. What is left: a reply that is not one of the
choices is retried once, then the email is dropped. It's the same rule as
the tagger veto: an email that can't be cleaned with confidence is
dropped, not trusted.

## Is an LLM needed at all?

A rule-only grouper is the baseline: exact match, plus a mention joining
an entity when its words (titles aside) are a subset of a mention already
in it, so "Lopez" joins "Maria Lopez". It merges every repeated string, so
it can't separate two Sams. On the labelled messages, a third to a half of
the messages with repeated PER, ORG or LOC mentions have mentions that
share words without being identical, which is where the two differ. The
LLM loop is used for a class only if it beats the rules on hand-grouped
messages.

## Caching

Each decision is keyed on the text, the mention and the entities offered,
the prompt version and the model. Re-running after a prompt change only
redoes decisions whose inputs changed.

## Later

**In the catalog.** A pseudonymised email is not a new sample: it is the
same sample, processed using newly extracted metadata. The groupings
belong in the catalog as annotations (a span plus an entity index, with
the LLM run as its source), reviewable in the labelling loop and set
beside human gold-set groupings. This needs `strata-contracts` to express
an entity id on a span, which it can't yet. The pseudonymised text itself
is a stage output, keyed on its inputs' hashes, not a catalog entry.

**Cross-class links.** An EMAIL belongs to a PER, a URL to an ORG, so that
replacement keeps a fake name and its fake address consistent. A separate
step after per-class grouping.

**For SFT.** Freeze the dataset version of the 1,000 kept samples and
their annotations. SFT trains on this stage's output over that version.
Replacement runs later, on the fine-tuned model's output.

**The PhishNet copy.** A materialised export of the stage output: only the
pseudonymised text, never the originals, which hold real PII.

## Evaluation

- Groupings are scored per class as pairwise links (do two mentions share
  an entity?), with precision, recall and F1, and as the share of emails
  grouped exactly right, against messages grouped by hand.
- The gold set, once it exists, includes human groupings, so grouping
  errors are scored alongside missed PII.
- The hand audit of a random sample of kept emails bounds the leak rate
  until the gold set exists.
