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
A kept message's line also carries the spans it was masked with, as
``mask`` ([start, end, class]), which the grouping stage reads.
"""

import argparse
import json
import random
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


def blob_path(blobs: Path, checksum: str) -> Path:
    """Where a sample's bytes are, in the catalog's local blob store."""
    [found] = list(blobs.glob(f"{checksum[:2]}/{checksum[2:4]}/{checksum}*"))
    return found


def masked(text: str, spans: list[Span]) -> str:
    """The text with each span replaced by its class's placeholder.

    Overlapping spans are one placeholder, in the class of the first.
    """
    out, at = [], 0
    for start, end, label in sorted(spans):
        if start < at:
            continue
        out += [text[at:start], f"[{label}]"]
        at = end
    return "".join([*out, text[at:]])


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
    parser.add_argument("--audit", type=int, default=100, help="Kept messages to sample")
    parser.add_argument("--seed", type=int, default=0, help="Seeds the audit sample")
    parser.add_argument("--limit", type=int, default=None, help="Only this many, for a trial run")
    args = parser.parse_args(argv)

    project = Project.load(Path("."))
    settings = Settings.load(None)
    config = settings.catalogs.named(project.catalog.name)
    catalog = open_catalog(config)
    store = RunStore.open(project.runs_dir)
    label_set_id, _ = catalog.label_sets.get(project.label_set_name)
    blobs = Path(config.root) / "blobs"

    def path_of(sample) -> Path:
        return blob_path(blobs, sample.checksum)

    labelled = catalog.samples.labelled(label_set_id, project.collections, source="human")
    pool = catalog.samples.unlabelled(label_set_id, project.collections)
    if args.limit is not None:
        pool = pool[: args.limit]
    print(f"{len(pool):,} unlabelled message(s) to mask, {len(labelled):,} labelled by hand")

    pool_paths = [path_of(s) for s in pool]
    by_gliner = spans_from(args.gliner, pool_paths, store)
    by_tagger = spans_from(args.tagger, pool_paths, store)

    out = args.out
    (out / "texts").mkdir(parents=True, exist_ok=True)
    manifest, kept, reasons = [], [], Counter()

    for sample, path, mask, veto in zip(pool, pool_paths, by_gliner, by_tagger, strict=True):
        text = text_of(path)
        missed = unmasked_by(text, mask, veto)
        entry = {
            "checksum": sample.checksum,
            "source": "gliner",
            "spans": len(mask),
            "kept": missed == 0,
            "reason": "models agree" if missed == 0 else "tagger flags unmasked text",
            "unmasked_chars": missed,
        }
        reasons[entry["reason"]] += 1
        if entry["kept"]:
            entry["mask"] = [list(s) for s in mask]
            (out / "texts" / f"{sample.checksum}.txt").write_text(
                masked(text, mask), encoding="utf-8"
            )
            kept.append(sample.checksum)
        manifest.append(entry)

    answers = catalog.annotations.values_of(label_set_id, [s.id for s in labelled])
    for sample in labelled:
        value = answers.get(sample.id)
        spans = [(v.start, v.end, v.labels[0]) for v in getattr(value, "values", [])]
        text = text_of(path_of(sample))
        (out / "texts" / f"{sample.checksum}.txt").write_text(masked(text, spans), encoding="utf-8")
        manifest.append(
            {
                "checksum": sample.checksum,
                "source": "human",
                "spans": len(spans),
                "kept": True,
                "reason": "labelled by hand",
                "unmasked_chars": 0,
                "mask": [list(s) for s in spans],
            }
        )
        reasons["labelled by hand"] += 1

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
