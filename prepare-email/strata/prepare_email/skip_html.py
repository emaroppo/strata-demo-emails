"""HTML mail skipped in a label set, written as an answers file, so no reviewer is sent any.

    skip-html --config <config.toml> [--catalog <name>] --label-set <name> \\
        --collection <path> [--collection <path> ...] --out <file>

The stages keep a body with HTML in it (ADR 0003, as amended by ADR
0013): leaving it out is a project's choice, not the preparation's. This
is how a project makes that choice for a review queue. Every live sample
in the collections named that looks like a page, by :func:`.html.looks_like_html`,
gets a skip with source ``import``. A skip keeps a sample out of the
label set's review queue and out of its dataset versions alike.

Nothing is written to the catalog here. ``strata-catalog import-answers``
reads the file and writes the skips as one run; a skip never replaces an
answer, so a message someone already answered keeps what it has. The
file names the rule as its origin, and every row's batch says it too.

The file is written as plain JSON in the layout that command reads
(format 1), rather than through the catalog's own model of it, so that
this needs only a catalog that can be read.
"""

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from .html import DEFAULT_MIN_TAGS, looks_like_html

#: The answers file layout strata-catalog's import-answers reads.
ANSWERS_FORMAT = 1


def rule(min_tags: int = DEFAULT_MIN_TAGS) -> str:
    """The rule's name, as the file records it."""
    return f"prepare-email/looks_like_html@min_tags={min_tags}"


def html_skips(
    catalog, label_set: str, collections: Iterable[str], min_tags: int = DEFAULT_MIN_TAGS
) -> tuple[dict, int]:
    """An answers file skipping every HTML sample in ``collections``, and how many were read.

    The label set must already exist in ``catalog``: its schema goes into
    the file, which an import checks against the one it lands in.
    """
    _, schema = catalog.label_sets.get(label_set)
    rows = catalog.samples.matching(list(collections))
    skip = {"state": "skipped", "source": "import", "batch": rule(min_tags)}
    samples = [
        {"checksum": row.checksum, "rows": [skip]}
        for row in rows
        if looks_like_html(catalog.blobs.get(row.location).decode("utf-8"), min_tags)
    ]
    answers = {
        "format": ANSWERS_FORMAT,
        "catalog_id": f"rules/{rule(min_tags)}",
        "label_set": label_set,
        "schema": json.loads(schema.model_dump_json()),
        "sources": ["import"],
        "samples": samples,
    }
    return answers, len(rows)


def main(argv: list[str] | None = None) -> int:
    from strata.catalog.config import load_catalogs, open_catalog

    parser = argparse.ArgumentParser(
        prog="skip-html", description="HTML mail skipped in a label set."
    )
    parser.add_argument("--config", type=Path, required=True, help="the host's catalog config")
    parser.add_argument("--catalog", default="", help="a [catalog.<name>] in the config")
    parser.add_argument("--label-set", required=True, help="where the skips go")
    parser.add_argument(
        "--collection", action="append", required=True, metavar="PATH", help="look in this one"
    )
    parser.add_argument("--out", type=Path, required=True, help="the answers file to write")
    parser.add_argument("--min-tags", type=int, default=DEFAULT_MIN_TAGS)
    args = parser.parse_args(argv)

    catalog = open_catalog(load_catalogs(args.config).named(args.catalog))
    answers, read = html_skips(catalog, args.label_set, args.collection, args.min_tags)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(answers, indent=1) + "\n", encoding="utf-8")
    print(
        f"{read:,} sample(s) read, {len(answers['samples']):,} HTML; into {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
