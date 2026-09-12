"""Landing a prepared corpus's candidate spans as a starting point.

    strata-seed-email --project projects/my-emails --apply

Separate from converting, and separate from ingest, because it is the one
step here that writes annotations. What it lands are guesses — regexes and
an off-the-shelf model — so they go in under ``source="import"``, never as
something a person said. A reviewer correcting one is what turns it into an
answer, and an export is what records that.

Selection is stratified rather than random, and the reasoning is worth
keeping: the corpus is extremely skewed, one measured at 136,203 ``URL``
spans against 2,362 ``ORG``. A few hundred messages drawn at random hold
almost no ``ORG``; a model that never saw a class is confidently silent
about it, and uncertainty sampling never surfaces it either, because the
queue is then ranked by a score with nothing behind it.

The random remainder matters as much as the stratified core. Validation
membership is assigned from whatever is labelled, so a seed that is *only*
stratified yields a validation set with the same distortion, and the first
number a round reports would flatter itself.
"""

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from strata.catalog.prepared import PreparedIndex


def choose(samples: dict, size: int, per_class: int, rng) -> list[str]:
    """Every class first, then filled out randomly."""
    by_class: dict[str, list[str]] = defaultdict(list)
    for name, entry in samples.items():
        for span in _spans(entry):
            for label in span.labels:
                by_class[label].append(name)

    chosen: list[str] = []
    seen: set[str] = set()
    # Rarest first, so a scarce class gets its pick of the documents
    # carrying it before a common one has spent the budget
    for label in sorted(by_class, key=lambda c: len(by_class[c])):
        pool = [n for n in by_class[label] if n not in seen]
        rng.shuffle(pool)
        for name in pool[:per_class]:
            chosen.append(name)
            seen.add(name)

    remainder = [n for n in samples if n not in seen]
    rng.shuffle(remainder)
    chosen.extend(remainder[: max(0, size - len(chosen))])
    return chosen


def _spans(entry) -> list:
    value = getattr(entry, "value", None)
    return list(getattr(value, "values", None) or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--size", type=int, default=400, help="Messages in the seed")
    parser.add_argument("--per-class", type=int, default=25, help="Minimum per class")
    parser.add_argument("--random-seed", type=int, default=0)
    parser.add_argument("--apply", action="store_true", help="Write; otherwise report only")
    args = parser.parse_args(argv)

    from strata.catalog import CatalogError
    from strata.catalog.blobs import checksum_of
    from strata.catalog.config import load_catalogs, open_catalog
    from strata.labeller.project import Project

    project = Project.load(args.project)
    index = PreparedIndex.load(project.data_dir)
    if index is None:
        print(
            f"No prepared corpus under {project.data_dir}; run "
            f"'auto-labeller prepare' first.",
            file=sys.stderr,
        )
        return 1

    carrying = {name: e for name, e in index.samples.items() if _spans(e)}
    if not carrying:
        print("The prepared corpus carries no candidate spans; nothing to seed.")
        return 0

    rng = random.Random(args.random_seed)
    chosen = choose(carrying, args.size, args.per_class, rng)

    histogram: Counter = Counter()
    for name in chosen:
        for span in _spans(carrying[name]):
            histogram.update(span.labels)
    print(f"Seed of {len(chosen):,} message(s), carrying:")
    for label, n in histogram.most_common():
        print(f"    {label:11} {n:,}")

    if not args.apply:
        print("\nReport only. Pass --apply to write.")
        return 0

    try:
        catalog = open_catalog(load_catalogs(args.config).named(project.catalog.name))
    except CatalogError as e:
        print(e, file=sys.stderr)
        return 1
    label_set_id, _schema = catalog.label_sets.get(project.label_set_name)

    items, missing = [], 0
    for name in chosen:
        path = project.data_dir / name
        if not path.exists():
            missing += 1
            continue
        row = catalog.samples.by_checksum(checksum_of(path))
        if row is None:
            missing += 1
            continue
        items.append((row.id, carrying[name].value))

    # Not "human": nobody has looked at these. That distinction is the only
    # thing separating a reviewed label from a regex's guess, and an export
    # overwrites it with "human" the moment someone submits the task.
    written = catalog.annotations.annotate_many(label_set_id, items, source="import")
    print(f"\nSeeded {written.annotated:,} annotation(s) as source='import'")
    if written.kept:
        # Running the seed again after a review pass is the case this is
        # for: the reviewer's answers stand, and the guesses they replaced
        # do not come back.
        print(f"  {written.kept:,} left alone — a person had already answered them")
    if missing:
        print(f"  {missing:,} chosen file(s) were not in the catalog — run ingest first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
