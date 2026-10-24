"""Anonymise the corpus, keep what both models agree is clean, and draw an audit.

    uv run python scripts/anonymise.py --gliner RUN --tagger RUN [--out anonymised] [--audit 100]

Each live message nobody has labelled is masked with the GLiNER run: every
predicted span becomes a placeholder of its class, "[PER]". The tagger run
then reads the same message; if it flags any character GLiNER left
unmasked, the message is dropped, since a disagreement is where a leak is
likeliest. Messages a person labelled are masked with their own labels and
kept. Skipped and removed messages are left out.

Written under ``--out``, which is gitignored and must stay so: the masked
texts of kept messages (dropped ones are never written), a manifest with
one line per message saying what happened to it and why, and an audit
sheet of a random sample of kept messages for a person to read. The
audit's leak count bounds the rate for the whole set; the README says how.
``--keep-from``, ``--min-chars``/``--max-chars`` and ``--sample`` narrow
the messages before anything is predicted: to those an earlier run kept,
of a usable length, and a sample of them that takes every hand-labelled
one and draws the rest at random, with at least ``--url-share`` of it
holding a link. A kept message's line also carries the
spans it was masked with, as ``mask`` ([start, end, class]), which the
grouping stage reads.

``--cut`` names a label set whose spans are left out of every message,
footers and disclaimers already marked, say. The tagger can't drop a
message for what lies in them, and the written text doesn't have them;
the line lists them as ``cut``, the offsets of ``mask`` and ``cut`` both
being into the message as stored. A message with no answer there is cut
nowhere: nothing new is looked for. One with nothing left once cut is
dropped.
"""

import argparse
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

from strata.catalog.config import open_catalog
from strata.modelling import RunStore
from strata.modelling.handlers import predict
from strata.modelling.requests import PredictRequest
from strata.project import Project, Settings

Span = tuple[int, int, str]


def text_of(path: Path) -> str:
    # Bytes as stored: offsets count \r. docs/labelling-guidelines.md
    return path.read_bytes().decode("utf-8", errors="replace")


LINK = re.compile(r"https?://|www\.", re.IGNORECASE)


def has_link(text: str) -> bool:
    return bool(LINK.search(text))


#: Where a catalog that keeps its blobs elsewhere has them fetched to. Under
#: .state/, which is ignored: these are the messages.
CACHE = Path(".state/blob-cache")


class BlobFiles:
    """Each sample's bytes as a file on this host, fetched once through the catalog.

    Whether the catalog keeps them on this disk or in a bucket, the models
    read paths, so they are cached here.
    """

    def __init__(self, catalog, cache: Path = CACHE):
        self.catalog, self.cache = catalog, cache
        self.paths: dict[str, Path] = {}

    def fetch(self, checksums) -> None:
        wanted = sorted(set(checksums) - self.paths.keys())
        if wanted:
            self.paths.update(self.catalog.ensure_cached(wanted, self.cache))
        missing = [c for c in wanted if c not in self.paths]
        if missing:
            raise SystemExit(f"Not in this catalog: {', '.join(c[:12] for c in missing[:5])}")

    def path(self, checksum: str) -> Path:
        self.fetch([checksum])
        return self.paths[checksum]


def rendered(text: str, swaps: list[tuple[int, int, str]], cut: list[Span] = ()) -> str:
    """The text with each (start, end, new) put in, and what ``cut`` covers left out.

    Of overlapping swaps the first by start is kept. Swaps must lie
    outside the cut, as :func:`outside` leaves them.
    """
    gaps: list[tuple[int, int, str]] = []
    for start, end, _ in sorted(cut):
        if gaps and start <= gaps[-1][1]:
            gaps[-1] = (gaps[-1][0], max(gaps[-1][1], end), "")
        else:
            gaps.append((start, end, ""))
    out, at = [], 0
    for start, end, new in sorted([*gaps, *swaps], key=lambda s: s[:2]):
        if start < at:
            continue
        out += [text[at:start], new]
        at = end
    return "".join([*out, text[at:]])


def masked(text: str, spans: list[Span], cut: list[Span] = ()) -> str:
    """The text with each span replaced by its class's placeholder, and the cut left out.

    Overlapping spans are one placeholder, in the class of the first.
    """
    return rendered(text, [(s, e, f"[{label}]") for s, e, label in sorted(spans)], cut)


def outside(spans: list[Span], cut: list[Span]) -> list[Span]:
    """Each span less any part a cut covers; one a cut falls inside is two."""
    for cut_start, cut_end, _ in cut:
        spans = [
            piece
            for s, e, label in spans
            for piece in ((s, min(e, cut_start), label), (max(s, cut_end), e, label))
            if piece[0] < piece[1]
        ]
    return spans


def unmasked_by(text: str, mask: list[Span], other: list[Span]) -> int:
    """Characters ``other`` flags that ``mask`` leaves in clear, whitespace aside."""
    covered = {i for s, e, _ in mask for i in range(s, e)}
    return sum(
        1 for s, e, _ in other for i in range(s, e) if i not in covered and not text[i].isspace()
    )


def spans_from(run_id: str, paths: list[Path], store: RunStore) -> list[list[Span]]:
    found = predict(PredictRequest(run_id=run_id, paths=[str(p) for p in paths]), store)
    return [[(v.start, v.end, v.labels[0]) for v in f.value.values] for f in found]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gliner", required=True, help="Run id of the GLiNER model that masks")
    parser.add_argument("--tagger", required=True, help="Run id of the tagger that vetoes")
    parser.add_argument("--out", type=Path, default=Path("anonymised"))
    parser.add_argument(
        "--runs", type=Path, help="Where the runs are, if not the project's own runs/"
    )
    parser.add_argument(
        "--cache", type=Path, default=CACHE, help="Where messages are fetched to, if not local"
    )
    parser.add_argument("--audit", type=int, default=100, help="Kept messages to sample")
    parser.add_argument("--seed", type=int, default=0, help="Seeds the audit and --sample")
    parser.add_argument("--limit", type=int, default=None, help="Only this many, for a trial run")
    parser.add_argument(
        "--keep-from", type=Path, help="Only messages an earlier run's manifest kept"
    )
    parser.add_argument("--min-chars", type=int, default=0, help="Leave out shorter messages")
    parser.add_argument("--max-chars", type=int, default=None, help="Leave out longer messages")
    parser.add_argument(
        "--sample", type=int, help="This many: every hand-labelled one, the rest drawn at random"
    )
    parser.add_argument(
        "--url-share", type=float, default=0.0, help="At least this share of --sample has a link"
    )
    parser.add_argument(
        "--cut", metavar="LABEL_SET", help="Leave out what this label set's answers mark"
    )
    args = parser.parse_args(argv)

    project = Project.load(Path("."))
    settings = Settings.load(None)
    config = settings.catalogs.named(project.catalog.name)
    catalog = open_catalog(config)
    store = RunStore.open(args.runs or project.runs_dir)
    label_set_id, _ = catalog.label_sets.get(project.label_set_name)
    files = BlobFiles(catalog, args.cache)

    def path_of(sample) -> Path:
        return files.path(sample.checksum)

    labelled = catalog.samples.labelled(label_set_id, project.collections, source="human")
    # Candidate spans a corpus arrived with are nobody's judgement: those
    # messages are masked by the models like any unlabelled one
    pool = catalog.samples.unlabelled(label_set_id, project.collections) + (
        catalog.samples.labelled(label_set_id, project.collections, source="import")
    )
    if args.limit is not None:
        pool = pool[: args.limit]
    if args.keep_from is not None:
        entries = map(json.loads, args.keep_from.read_text(encoding="utf-8").splitlines())
        before = {e["checksum"] for e in entries if e["kept"]}
        pool = [s for s in pool if s.checksum in before]
        labelled = [s for s in labelled if s.checksum in before]
    # Fetched together rather than one by one, once the pool is as narrow as
    # it gets without reading a message
    files.fetch(s.checksum for s in [*pool, *labelled])
    if args.min_chars or args.max_chars is not None:
        longest = args.max_chars if args.max_chars is not None else float("inf")

        def fits(sample) -> bool:
            return args.min_chars <= len(text_of(path_of(sample))) <= longest

        pool = [s for s in pool if fits(s)]
        labelled = [s for s in labelled if fits(s)]
    if args.sample is not None:
        labelled = labelled[: args.sample]
        linked = {s.checksum: has_link(text_of(path_of(s))) for s in [*pool, *labelled]}
        rng = random.Random(args.seed)
        with_link = [s for s in pool if linked[s.checksum]]
        have = sum(linked[s.checksum] for s in labelled)
        want = max(0, math.ceil(args.url_share * args.sample) - have)
        chosen = rng.sample(with_link, min(len(with_link), want))
        picked = {s.checksum for s in chosen}
        others = [s for s in pool if s.checksum not in picked]
        pool = chosen + rng.sample(
            others, min(len(others), args.sample - len(labelled) - len(chosen))
        )
        links = sum(linked[s.checksum] for s in [*labelled, *pool])
        print(f"sampled {len(labelled) + len(pool):,}: {links:,} with a link")
    print(f"{len(pool):,} unlabelled message(s) to mask, {len(labelled):,} labelled by hand")

    cuts: dict[int, list[Span]] = {}
    if args.cut is not None:
        cut_set_id, _ = catalog.label_sets.get(args.cut)
        marks = catalog.annotations.values_of(cut_set_id, [s.id for s in [*pool, *labelled]])
        cuts = {
            sample_id: [(v.start, v.end, v.labels[0]) for v in getattr(value, "values", [])]
            for sample_id, value in marks.items()
        }
        print(f"{sum(1 for c in cuts.values() if c):,} message(s) with something to cut")

    pool_paths = [path_of(s) for s in pool]
    by_gliner = spans_from(args.gliner, pool_paths, store)
    by_tagger = spans_from(args.tagger, pool_paths, store)

    out = args.out
    (out / "texts").mkdir(parents=True, exist_ok=True)
    manifest, kept, reasons = [], [], Counter()

    def record(sample, source: str, text: str, mask: list[Span], reason: str, missed=0) -> None:
        """A message's manifest line, and its masked text if it is kept."""
        cut = cuts.get(sample.id, [])
        body = masked(text, mask, cut)
        if not missed and not body.strip():
            reason = "nothing left once cut"
        entry = {
            "checksum": sample.checksum,
            "source": source,
            "spans": len(mask),
            "kept": reason in ("models agree", "labelled by hand"),
            "reason": reason,
            "unmasked_chars": missed,
        }
        reasons[reason] += 1
        if entry["kept"]:
            entry["mask"] = [list(s) for s in mask]
            if cut:
                entry["cut"] = [list(s) for s in cut]
            (out / "texts" / f"{sample.checksum}.txt").write_text(body, encoding="utf-8")
            if source == "gliner":
                kept.append(sample.checksum)
        manifest.append(entry)

    for sample, path, mask, veto in zip(pool, pool_paths, by_gliner, by_tagger, strict=True):
        text = text_of(path)
        cut = cuts.get(sample.id, [])
        mask = outside(mask, cut)
        missed = unmasked_by(text, mask + cut, veto)
        reason = "models agree" if missed == 0 else "tagger flags unmasked text"
        record(sample, "gliner", text, mask, reason, missed)

    answers = catalog.annotations.values_of(label_set_id, [s.id for s in labelled])
    for sample in labelled:
        value = answers.get(sample.id)
        spans = [(v.start, v.end, v.labels[0]) for v in getattr(value, "values", [])]
        spans = outside(spans, cuts.get(sample.id, []))
        record(sample, "human", text_of(path_of(sample)), spans, "labelled by hand")

    with open(out / "manifest.jsonl", "w", encoding="utf-8") as f:
        for entry in manifest:
            f.write(json.dumps(entry) + "\n")

    sample = random.Random(args.seed).sample(kept, min(args.audit, len(kept)))
    with open(out / "audit.md", "w", encoding="utf-8") as f:
        f.write(
            f"# Audit: {len(sample)} kept messages, drawn at random (seed {args.seed})\n\n"
            "Read each against docs/labelling-guidelines.md. Tick it if anything that\n"
            "should be masked is still in clear: a name, an organisation, a place, a\n"
            "date, an address, a number, a link, an attachment's name. Placeholders in\n"
            "the wrong class don't count; only what's left unmasked does.\n\n"
        )
        for n, checksum in enumerate(sample, 1):
            body = (out / "texts" / f"{checksum}.txt").read_text(encoding="utf-8")
            f.write(f"## {n}. {checksum[:12]}\n\n- [ ] leaks\n\n```\n{body}\n```\n\n")

    total_kept = sum(1 for e in manifest if e["kept"])
    print(f"kept {total_kept:,} of {len(manifest):,}")
    for reason, count in reasons.most_common():
        print(f"  {count:6,}  {reason}")
    print(f"audit sheet: {out / 'audit.md'} ({len(sample)} messages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
