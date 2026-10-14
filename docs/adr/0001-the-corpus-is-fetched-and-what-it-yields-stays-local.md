# 1. The corpus is fetched, and what it yields stays local

**Status:** accepted

## The decision

The mail this project runs on is not in the repository. It is a public
archive, fetched by the person running the project into `data/`, and
everything derived from it — the catalog, model runs, datasets, masked
output, labelling notes, audit and judging sheets — is gitignored. The
repository holds code, configuration, the labelling guide and results as
numbers. Examples in documentation are invented.

## Why

The messages are somebody's, even when the archive is public. Shipping
them would make this repository one more copy; shipping what was derived
from them is no better while detection still misses things, and a masked
message that leaks one name is still that person's mail. Numbers and
invented examples show what the project does without republishing anyone.

## Consequences

- A stranger's clone runs on any directory of `.eml` files; the committed
  configuration names a local catalog, so nothing needs installing.
- Anything that quotes the mail — the audit sheet, the grouping review,
  the judging reports, an LLM's stated reasons — lives in `notes/` or
  `anonymised*/`, both ignored, and never in a commit message.
- The model that groups entities runs on hardware of our own
  ([ADR 7](0007-the-grouping-model-runs-locally-with-reasoning.md)): the
  mail is not sent to a hosted service.
- The project is to move to a corpus of mostly private correspondence
  that is the standard research set, fetched the same way.
