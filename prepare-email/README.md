# strata-prepare-email

Mail into a catalog: the `email` sample type, and two preparers that turn
what mail arrives as into what the type stores. A plugin to
`strata-catalog`, found through its entry points, needing nothing beyond
the standard library's mail parser.

```bash
uv add strata-prepare-email
uv add "strata-prepare-email[seed]"      # strata-seed-email; pulls in strata-labeller
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
annotation the corpus arrived with. `ingest` then catalogues it.

## Seeding

`strata-seed-email` lands a prepared corpus's candidate spans, from regexes
or another model, as a starting point for a review queue. They go in under
the `import` source, never as something a person said, and the selection
is stratified over classes with a random remainder, so the first rounds
see every class and validation is not drawn from the same distortion.

```bash
strata-seed-email --project projects/my-emails          # report
strata-seed-email --project projects/my-emails --apply
```

## Tests

```bash
uv run pytest packages/prepare-email
```

Includes the catalog's `PreparerContract`, run against both preparers.
