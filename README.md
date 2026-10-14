# Named entities in mail, on a strata catalog

A strata project: mail arrives as `.eml` files, a converter turns each
message body into a document, and span models learn to find people,
organisations, places, dates, addresses, phone numbers, URLs and
attachments in it, so a message can be anonymised. What the project labels,
from which catalog, with which model, is `project.toml`; where things are
on this machine is `config.toml`; the loop is `strata-labeller`.

The converter is the point. `prepare-email/` is a plugin written the way
one is written outside strata: its own distribution, registered through
the catalog's entry points (`strata.sample_types` for the `email` type,
`strata.preparers` for the two converters), tested against the catalog's
own conformance suite. Nothing in strata knows it exists. Its README says
what it does.

## An example

A message made up for this README (no one in it exists), and what the
fine-tuned GLiNER model makes of it:

```
Hi Dana,

Thanks for joining the call with Northfield Tenants Union on Tuesday. As
promised, I've attached the draft budget (budget-draft-v3.xlsx) and the
venue details for the Riverside town hall on March 12 at 6:30pm.

Senator Maria Lopez will open, and Sam Okafor from the Daily Ledger has
asked for ten minutes afterwards. The hall is at 41 Mill Street,
Riverside OH 44000; parking is behind the library.

The sign-up page is live at https://www.example.org/townhall-rsvp if you
want to share it.

Best,
Ruth Adler
Field Director, Coalition for Fair Housing
ruth.adler@example.org | (555) 014-2297
```

```
Hi [PER],

Thanks for joining the call with [ORG] on [DATE]. As
promised, I've attached the draft budget (budget-draft-v3.xlsx) and the
venue details for the [LOC] town hall on [DATE].

[PER] will open, and [PER] from [ORG] has
asked for ten minutes afterwards. The hall is at [LOC]; parking is behind the library.

The sign-up page is live at [URL] if you
want to share it.

Best,
[PER]
Field Director, [ORG]
[EMAIL] | [PHONE]
```

Every name, organisation, place, date and contact detail is masked, the
title goes with the name ("Senator Maria Lopez" is one `[PER]`), and the
address is one `[LOC]` across its line break. One thing is missed: the
attachment's name, `budget-draft-v3.xlsx`, is left in clear.

That is why GLiNER does not work alone. A second model, the BIO tagger,
reads the same message, and here it flags part of that file name; since
the tagger sees something GLiNER left unmasked, this message is dropped
rather than kept (`scripts/anonymise.py`). On the corpus this keeps 29% of
the messages: a strict filter, but the corpus is large enough to afford it.

## Running it

```bash
uv sync --extra model --extra experiment
# put the corpus under data/raw, one .eml per message (see below)
uv run strata-labeller prepare
uv run strata-labeller ingest
uv run strata-labeller train
uv run strata-labeller report
```

No database, no object store and no GPU: the committed `config.toml`
names a SQLite index and a directory of blobs under `catalog/`. A host
with a real catalog keeps its own file and names it in `$STRATA_CONFIG`.
A Label Studio at the address in `config.toml` adds the review step
(`push`, `export`, with its key in `$LABEL_STUDIO_API_KEY`); without one
the loop still trains and reports.

The candidate spans a corpus arrives with, if any, land at ingest as an
import batch: trusted and trained on, never counted as something a person
said, and spot-checked where the model disagrees (`push --review-imports`).

## Labelling

`docs/labelling-guidelines.md` is the rulebook, at version 1: what each
class covers, where a span starts and ends, and the conventions an
anonymiser needs (a title is part of the name, a URL may keep its
brackets if they balance, a skip means the message is out of scope). Its
examples are invented; the guide quotes no one from the mail.

## Comparing approaches

`docs/anonymisation-approaches.md` sets out the ways to anonymise mail;
`docs/roadmap.md` is the plan for comparing them fairly, starting with a
random, double-checked gold set no approach trains or tunes on. Until that
exists, the numbers below are on an **interim dev set**: the 29 validation
messages of dataset version 7. They are not random, they were used to
choose settings, and 29 messages is few, so read them as a direction, not
a size.

Every comparison is an experiment file under `comparisons/`, run and set
side by side with:

```bash
uv run strata-experiment run comparisons/tagger.toml
uv run strata-experiment report comparisons/*.toml --markdown
```

### Results so far: dev (emails v7 val, 29 messages)

Two models: the BIO tagger (DistilBERT, `text-span`) and GLiNER
(`gliner-span`, `knowledgator/gliner-pii-base-v1.0` fine-tuned for 30
epochs, reading URLs as one word). Mean ± spread over three seeds.

| approach | strict F1 | partial F1 | entities leaked ↓ | fragmented ↓ | character recall |
|---|---|---|---|---|---|
| tagger | 0.723 ± 0.010 | 0.868 ± 0.011 | **0.108 ± 0.008** | 0.065 | **0.972** |
| GLiNER, fine-tuned | **0.822 ± 0.011** | **0.895 ± 0.003** | 0.129 ± 0.009 | **0.008** | 0.898 |
| GLiNER, zero-shot (best of three checkpoints) | 0.533 | 0.630 | 0.477 | 0.004 | 0.375 |

*Leaked*: share of true entities with any character left unmasked.
*Fragmented*: share split across several placeholders ("Dear [PER] [PER]").

GLiNER finds entities more exactly and almost never splits one; the tagger
still leaves the fewest unmasked. Zero-shot, no checkpoint knows this
guide's conventions well enough to be used as it is.

### How each improves with data

Strict F1 on dev, training on nested shares of the 117 training messages:

| training messages | 25% | 50% | 75% | 100% |
|---|---|---|---|---|
| tagger | 0.596 | 0.670 | 0.681 | 0.723 |
| GLiNER | 0.620 | 0.754 | 0.757 | 0.822 |

Neither curve has flattened, and GLiNER's leak rate falls faster (32% at a
quarter of the data, 13% at all of it): more labels should still pay, most
of all for organisations, the weakest class for both.

## The corpus

Not vendored. This project was run on a public archive of mail; the
messages are somebody's, so they are fetched rather than shipped, and
`data/` is ignored, as are the catalog, the runs and the experiment
ledger. Any directory of `.eml` files under `data/raw` works.
