# Named entities in mail, on a strata catalog

A strata project: mail arrives as `.eml` files, a converter turns each
message body into a document, and a span tagger learns to find people,
organisations, places, dates, addresses, phone numbers, URLs and
attachments in it. What the project labels, from which catalog, with
which model, is `project.toml`; where things are on this machine is
`config.toml`; the loop is `strata-labeller`.

The converter is the point. `prepare-email/` is a plugin written the way
one is written outside strata: its own distribution, registered through
the catalog's entry points (`strata.sample_types` for the `email` type,
`strata.preparers` for the two converters), tested against the catalog's
own conformance suite. Nothing in strata knows it exists. Its README says
what it does.

## Running it

```bash
uv sync --extra model
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
(`push`, `export`); without one the loop still trains and reports.

The candidate spans a corpus arrives with, if any, land at ingest as an
import batch: trusted and trained on, never counted as something a person
said, and spot-checked where the model disagrees (`push --review-imports`).

## The corpus

Not vendored. This project was run on a public archive of mail; the
messages are somebody's, so they are fetched rather than shipped, and
`data/` is ignored. Any directory of `.eml` files under `data/raw` works.
