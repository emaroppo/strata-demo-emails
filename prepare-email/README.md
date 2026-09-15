# strata-prepare-email

Mail into a catalog: the `email` sample type, and two preparers that turn
what mail arrives as into what the type stores. A plugin to
`strata-catalog`, found through its entry points, needing nothing beyond
the standard library's mail parser.

```bash
uv add strata-prepare-email
```

## What it adds

| entry point | name | what it does |
|---|---|---|
| `strata.sample_types` | `email` | a message body as a document, subclassing `Text` |
| `strata.preparers` | `eml` | `.eml` files into `email` documents |
| `strata.preparers` | `email-json` | a message JSON export into `email` documents |

One sample is one message body, as characters. Headers are metadata on
the sample, never prepended to the text, so a span annotated against the
body keeps its offsets. Threads are not grouped yet.

A prepared corpus is a directory of documents and a `prepared.json` index
of what the conversion knew: sender, subject, date, and any candidate
annotation the corpus arrived with. `ingest` then catalogues it, and lands
those candidate spans in the same pass as an import batch — trusted and
trained on, never as something a person said, and spot-reviewed with
`push --review-imports` where the model disagrees with them. Nothing in
this package writes to a catalog.

## Tests

```bash
uv run pytest prepare-email     # from the emails demo project, whose plugin this is
```

Inside the strata workspace: `uv run pytest packages/prepare-email` from its root.

Includes the catalog's `PreparerContract`, run against both preparers.
