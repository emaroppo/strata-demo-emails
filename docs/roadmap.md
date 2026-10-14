# Roadmap: a comparison of approaches to anonymising mail

The aim is a fair, reproducible answer to "which approach anonymises this
mail best, at what cost?": the BIO tagger, span classification (GLiNER),
local LLMs, rules, and combinations, each scored on the same messages by the
same code. `docs/anonymisation-approaches.md` describes the approaches;
this file is the order of work and what each step must leave behind.

Nothing below is comparable until steps 0 and 1 are done. Every number so
far (val F1 0.70 on 29 messages, holdout F1 0.55 on 19) is on a small,
non-random set, and the holdout's labels have since changed.

## 0. Ground rules

Before a single gold message is labelled, because changing any of these
afterwards means relabelling the gold set.

- [x] **Freeze the guide.** `docs/labelling-guidelines.md` is at version
      1, and the gold set records the version it was labelled under. A
      later rule change is a new version and a new gold release, not an
      edit. Settled: URL brackets may be included or not, as long as they
      balance; hashtags aren't entities but entities inside them are; a
      skip means what it means in strata, nothing applicable; a title
      beneath a name is either inside the PER or has what's inside it (a
      place, an organisation) labelled with its own class.
- [x] **HTML policy: excluded.** HTML source (1.2% of the corpus) is left
      out by both preparers and counted as `skipped_html`, and the 146 HTML
      samples already in the catalog are tombstoned. The gold set is drawn
      after this, so it describes what a model will actually see.
- [x] **Text defects: accepted.** Words run together where a line break
      was (about 1% of messages) are kept as a known condition of the
      corpus, already present in the export it came from. Every approach
      sees the same text, and the write-up says so.
- [x] **Whitespace trimmed.** Export trims every span against its
      document, `strata-labeller trim` repaired the ones already stored,
      and the preparer trims candidates too, so gold spans never start
      inside a run of spaces.

## 1. The gold set

A fixed set of messages, labelled to the frozen guide, that no approach
trains on, tunes on or selects with. It is the only set results are
reported on.

**None of the messages labelled so far go into it.** All 146 stay training
data, for three reasons:
- They aren't a random sample: the review queue served them least
  confident first, so they over-represent what the old model found hard.
- They weren't labelled the way gold must be: with model pre-annotations
  showing, without a blind second pass, and under a guide that changed
  while they were being labelled.
- Some have already been used to choose: the 29 validation messages
  decided between the first trained models.

**Sampling.** Drawn uniformly at random, with a recorded seed, from the
live messages nobody has labelled: after the HTML policy, never from the
review queue. Leaving the 146 out of the draw biases it by about 1% of the
corpus, which is negligible, and avoids a second, conflicting label on
them. Messages answered only by an unreviewed import are fair game: gold
labels are made from scratch. The 25 remaining skips stay out of both sets
until the follow-up on skips is done. Report results per length bucket and
for messages with no entities, rather than stratifying, so the headline
number describes the real distribution.

**Size.** Labelled messages so far average about 15 spans each, but the
rare classes are thin: 29 validation messages held 7 phone numbers and 14
email addresses. Target **150 messages** (roughly 2,000 spans), enough for
a few dozen of each class except ATTACHMENT, and an overall F1 known to
within about ±0.02. ATTACHMENT will stay too rare to score from a random
sample; report it as unscored rather than inflate it.

**Labelling protocol.**
- [ ] Pushed with `--no-predictions`: no model pre-annotations, so the gold
      set isn't anchored to one of the systems it will judge.
- [ ] Every gold message gets a blind second pass (`strata-labeller audit`)
      after a gap of days, and disagreements are adjudicated against the
      guide. The agreement between passes is reported: it is the ceiling no
      model can be expected to beat.
- [ ] Skips are not allowed in the gold set: a message is either labelled
      (empty counts) or removed by the HTML policy, and the reason is
      recorded.

**Freezing.** The gold set is a named, versioned dataset in the catalog
with an explicit membership list (`given_split`), not a ratio drawn at
run time. Its annotation digest and guide version are recorded; a change
is a new release (`gold v2`) and results name the release they were
scored on. The current `anonymise-study` holdout (19 messages) is retired.

**Done when:** 150 messages labelled twice and adjudicated, agreement
reported, the dataset frozen, and the existing tagger scored on it once
as the first row of the results table.

## 2. A development set, separate from gold

Model selection, threshold tuning and early stopping need held-out data
too, and doing them on the gold set leaks it. A random **dev set** of
about 50 messages, labelled the same way, used freely. The training pool
is everything else that is labelled, and keeps growing through the review
loop.

**Until it exists, the interim dev set** is the labelling loop's
validation split: 29 of the 146 labelled messages, the same 29 in the
dataset versions trained since the export (v6 and v7). When the random dev
set lands, they go back into training.

**Interim results on the dev set** are allowed, so comparing approaches
doesn't wait on gold, under three rules:
- Every interim number says so: "dev (29, non-random)", wherever it
  appears, the results table included.
- It is read as a direction, not a size. The set is small (an F1 interval
  of roughly ±0.05–0.08), not random, and used for selection, so it runs
  optimistic.
- Whatever wins on dev is scored on gold before anything is concluded,
  and the gold score replaces the dev score rather than sitting beside it.

When the random dev set lands, interim results move to it under the same
rules, less "non-random".

## 3. One way of scoring

- [ ] Every approach is an `experiment.toml` whose `evaluate` stage runs on
      the gold set with the same tasks: `entities` (strict and partial,
      per class) and `mask` (leaked, fragmented, merging, truncated,
      spilled, spurious, character recall).
- [ ] **A primary metric, chosen now.** For anonymisation the costly
      failure is a leak, so the lead is **leaked rate** (or character
      recall), with fragmented and merging beside it; entity F1 is
      reported but does not decide.
- [ ] **Uncertainty.** Bootstrap over messages for a confidence interval
      on each headline number, and **at least three seeds** per trained
      approach. One run each proved misleading: the cased encoder looked
      like an obvious improvement and scored 0.62 against 0.71, from 32
      fragmented entities against 21.
- [ ] **Per-class partial F1 recorded,** not only overall. Today only the
      overall partial number is kept.
- [ ] **Cost columns:** training time, inference time per message, memory,
      and whether it runs on the one consumer GPU.

## 4. Baselines

Floors that every learned approach must beat, cheap to run:

- [ ] Regex for EMAIL, PHONE, URL (and handles), nothing else.
- [ ] Presidio, out of the box, as an off-the-shelf reference.
- [ ] The current tagger (DistilBERT uncased, BIO), three seeds.

## 5. Approaches, in order

Following `docs/anonymisation-approaches.md`, each one row (or a small
grid) in the results table:

1. **Tagger + post-processing.** The same predictions through
   `merge-adjacent`, to measure how much fragmentation is a decoding
   problem. Needs harmonisers in strata.
2. **Tagger variants.** A stronger encoder (DeBERTa-v3) with word-level
   labels and constrained decoding; cased only together with those.
3. **Regex layered over the best tagger** for the pattern classes, where
   the tagger over-predicts today (EMAIL and PHONE at about twice the true
   count).
4. **GLiNER,** zero-shot first (partial F1 is the fair number, since it
   doesn't know the guide's conventions), then fine-tuned on the training
   pool. Needs a GLiNER model wrapper in strata.
5. **Local LLM,** prompted, then QLoRA fine-tuned, with constrained output
   mapped back to character spans.
6. **Hybrid:** the best cheap model proposes, the best LLM repairs, if the
   gap justifies the latency.

## 6. How much data each approach needs

Small labelled data is the condition this project lives in, so the
comparison should say how each approach scales: train on 25, 50, 100 and
all of the training pool (fixed nested subsets), score each on gold. An
approach that is best at 150 labels and one that is best at 1,000 are
different recommendations.

## 7. Write-up

- [ ] A results table in the README: one row per approach, the primary
      metric with its interval, entity F1, the failure-mode rates, cost.
      Every number says which set it was scored on. While only dev numbers
      exist, the table shows them, labelled "dev (29, non-random)"; as an
      approach is scored on gold, its gold score replaces its dev score.
- [ ] Error analysis per approach on the gold set: what it leaks, what it
      fragments. Kept in `notes/` when it quotes the corpus.
- [ ] Every row reproducible from a committed `experiment.toml` and a named
      gold release.

## What strata needs for this

Gaps found along the way, to land in the strata repositories:

- Harmonisers (`merge-adjacent` and friends) as a stage between
  prediction and scoring.
- A GLiNER wrapper, and later an LLM one, as `Model` implementations.
- Bootstrap intervals and seed aggregation in experiment reports.
- Per-class partial F1 in the `entities` task.
- A `compare` that refuses across gold releases (already in the strata
  TODO).
