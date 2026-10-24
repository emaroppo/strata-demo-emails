"""Export the judged, indexed messages as examples for the template-writing LoRA.

    uv run --no-sync python scripts/export_sft.py [--out datasets/template-sft]

Reads both indexed sets written by ``group.py``, the DNC one and the Enron
one, and keeps a message only if its verdict in ``notes/`` is ``keep``;
messages not judged yet are left out, so a rerun picks them up. The Enron
report notifications in ``notes/enron-drop-reports.jsonl`` go too. Each
example gets its subject, untouched: Enron's from the catalog's sample
metadata, DNC's from MongoDB through ``notes/dnc-mongo-map.jsonl`` (read
with ``mongosh``, so nothing new is installed). ``urls`` and
``attachments`` are derived from the body's own placeholders.

Written to ``--out``/``examples.jsonl``, gitignored: it holds real
subjects. Dropping long bodies, collapsing near-duplicates and the split
happen on the training side, which has the base model's tokenizer.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from strata.catalog.config import open_catalog
from strata.project import Project, Settings

ROOT = Path(__file__).resolve().parent.parent
CORPORA = {
    "dnc": ("anonymised-1250-indexed", "notes/verdicts-1250.jsonl"),
    "enron": ("anonymised-enron-4000-indexed", "notes/verdicts-enron.jsonl"),
}
PLACEHOLDER = re.compile(r"\[([A-Z]+)_\d+\]")
MONGO = "mongodb://localhost:27017/phishnet_sft_datasources"


def read_jsonl(path: Path) -> list[dict]:
    """Every whole line; a line still being written by a running job is skipped."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def verdicts(path: Path, reinstate_parent: bool) -> dict[str, str]:
    """The last verdict per checksum, with parent/subsidiary drops reinstated if asked."""
    found = {}
    for row in read_jsonl(path):
        verdict = row["verdict"]
        if (
            reinstate_parent
            and verdict == "drop-grouping"
            and "parent/subsidiary" in (row.get("note") or "")
        ):
            verdict = "keep"
        found[row["checksum"]] = verdict
    return found


def enron_subjects(checksums: list[str]) -> dict[str, str | None]:
    """Subjects from the catalog, opened as the ``enron/`` project opens it."""
    here = Path.cwd()
    os.chdir(ROOT / "enron")
    try:
        project = Project.load(Path("."))
        settings = Settings.load(None)
        catalog = open_catalog(settings.catalogs.named(project.catalog.name))
    finally:
        os.chdir(here)
    ids = {}
    for checksum in checksums:
        row = catalog.samples.by_checksum(checksum)
        if row is not None:
            ids[row.id] = checksum
    with catalog.engine.connect() as conn:
        metadata = catalog.samples.metadata(conn, list(ids))
    return {ids[i]: metadata.get(i, {}).get("subject") for i in ids}


def dnc_subjects(checksums: list[str]) -> dict[str, str | None]:
    """Subjects from MongoDB: the main message's Subject header in each mapped document."""
    mongo_ids = {
        row["mongo_id"]: row["checksum"]
        for row in read_jsonl(ROOT / "notes/dnc-mongo-map.jsonl")
        if row["checksum"] in set(checksums)
    }
    script = """
const ids = JSON.parse(process.env.MONGO_IDS).map(i => ObjectId(i));
const out = {};
db.podesta_single_messages.find({_id: {$in: ids}}, {messages: 1}).forEach(d => {
  const main = d.messages.find(m => m.is_main);
  out[d._id.toString()] = main && main.headers ? (main.headers.Subject ?? null) : null;
});
print(JSON.stringify(out));
"""
    result = subprocess.run(
        ["mongosh", "--quiet", MONGO, "--eval", script],
        capture_output=True,
        text=True,
        check=True,
        env={"MONGO_IDS": json.dumps(list(mongo_ids)), "PATH": "/usr/bin:/bin"},
    )
    found = json.loads(result.stdout.strip().splitlines()[-1])
    return {mongo_ids[i]: subject for i, subject in found.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "datasets/template-sft")
    parser.add_argument(
        "--reinstate-parent-subsidiary",
        action="store_true",
        help="Keep the Enron messages dropped only for a parent/subsidiary grouping",
    )
    parser.add_argument(
        "--keep-empty-subjects",
        action="store_true",
        help="Keep messages with no subject, with an empty one, rather than drop them",
    )
    args = parser.parse_args(argv)

    reports = {row["checksum"] for row in read_jsonl(ROOT / "notes/enron-drop-reports.jsonl")}
    examples, counts = [], Counter()
    for corpus, (indexed, verdict_file) in CORPORA.items():
        judged = verdicts(ROOT / verdict_file, args.reinstate_parent_subsidiary)
        chosen = []
        for row in read_jsonl(ROOT / indexed / "manifest.jsonl"):
            checksum = row["checksum"]
            if not row["kept"]:
                counts[f"{corpus}: not kept by grouping"] += 1
            elif checksum not in judged:
                counts[f"{corpus}: not judged yet"] += 1
            elif judged[checksum] != "keep":
                counts[f"{corpus}: verdict {judged[checksum]}"] += 1
            elif checksum in reports:
                counts[f"{corpus}: report notification"] += 1
            else:
                chosen.append(checksum)
        subjects = (dnc_subjects if corpus == "dnc" else enron_subjects)(chosen)
        for checksum in chosen:
            subject = subjects.get(checksum)
            if subject is None or not subject.strip():
                if not args.keep_empty_subjects:
                    counts[f"{corpus}: no subject"] += 1
                    continue
                subject = ""
            body = (ROOT / indexed / "texts" / f"{checksum}.txt").read_text(encoding="utf-8")
            classes = set(PLACEHOLDER.findall(body))
            examples.append(
                {
                    "checksum": checksum,
                    "corpus": corpus,
                    "subject": subject.strip(),
                    "urls": "URL" in classes,
                    "attachments": "ATTACHMENT" in classes,
                    "body": body,
                }
            )
            counts[f"{corpus}: exported"] += 1

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "examples.jsonl", "w", encoding="utf-8") as f:
        for example in examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    flags = Counter((e["urls"], e["attachments"]) for e in examples)
    print(f"urls: {sum(v for (u, _), v in flags.items() if u)}", end=", ")
    print(f"attachments: {sum(v for (_, a), v in flags.items() if a)}")
    print(f"wrote {len(examples)} examples to {args.out / 'examples.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
