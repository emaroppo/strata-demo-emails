"""Group the anonymised set's masked spans into entities, and number them.

    uv run python scripts/group.py [--llm http://host:port] [--limit N]
    uv run python scripts/group.py --review 40          # a sheet to group by hand
    uv run python scripts/group.py --score notes/grouping-review.md [--llm URL]

Reads ``anonymised/manifest.jsonl`` (written by ``anonymise.py``) for the
kept messages and the spans each was masked with. Without ``--llm`` the
rules group them, the baseline; with it, PER, ORG and LOC mentions go one
by one to that llama.cpp server. Written under ``--out``, gitignored like
``anonymised/``: each message with ``[PER_1]``-style placeholders, and a
manifest saying per message what was found, how many calls it took, and
whether it was kept. A message the chooser can't answer for is dropped.

``--review N`` writes a sheet of N hand-labelled messages, with their
mentions numbered, for a person to group (into ``notes/``, gitignored: it
holds real text). ``--score`` reads that sheet back and sets the rules
beside the LLM, per class: with ``--llm``, the model both with and without
its reasoning (``--no-think`` runs the set without it).
``docs/entity-grouping.md`` says why.
"""

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

from anonymise import blob_path, text_of
from group_entities import GroupingFailed, Mention, group_message, indexed
from group_entities.cache import CachedChooser
from group_entities.llm import LlamaCppChooser
from group_entities.loop import DECIDED

from strata.catalog.config import open_catalog
from strata.project import Project, Settings

CACHE = Path(".state/grouping/decisions.jsonl")


def blobs_dir() -> Path:
    project = Project.load(Path("."))
    config = Settings.load(None).catalogs.named(project.catalog.name)
    open_catalog(config)  # refuses early if the catalog isn't this project's
    return Path(config.root) / "blobs"


def kept(manifest: Path) -> list[dict]:
    entries = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    entries = [e for e in entries if e["kept"]]
    if entries and "mask" not in entries[0]:
        sys.exit(f"{manifest} has no spans: rerun scripts/anonymise.py, which now records them")
    return entries


def mentions_of(text: str, mask: list) -> list[Mention]:
    spans = sorted((s, e, c) for s, e, c in mask)
    return [Mention(i, s, e, c, text[s:e]) for i, (s, e, c) in enumerate(spans)]


def chooser_for(url: str | None, think: bool = True) -> CachedChooser | None:
    if url is None:
        return None
    return CachedChooser(LlamaCppChooser(url if "://" in url else f"http://{url}", think), CACHE)


# --- the run ---------------------------------------------------------------


def run(args, blobs: Path) -> None:
    entries = kept(args.manifest)[: args.limit]
    chooser = chooser_for(args.llm, think=not args.no_think)
    out = args.out
    (out / "texts").mkdir(parents=True, exist_ok=True)
    lines, outcomes, calls = [], Counter(), 0
    started = time.monotonic()
    for n, entry in enumerate(entries, 1):
        text = text_of(blob_path(blobs, entry["checksum"]))
        mentions = mentions_of(text, entry["mask"])
        line = {"checksum": entry["checksum"], "source": entry["source"]}
        try:
            grouped = group_message(text, mentions, chooser)
        except GroupingFailed as e:
            line |= {"kept": False, "reason": str(e)}
        else:
            per_class = Counter(e.cls for e in grouped.entities)
            line |= {
                "kept": True,
                "entities": dict(sorted(per_class.items())),
                "calls": grouped.calls,
            }
            calls += grouped.calls
            (out / "texts" / f"{entry['checksum']}.txt").write_text(
                indexed(text, grouped.entities), encoding="utf-8"
            )
        outcomes["kept" if line["kept"] else "failed"] += 1
        lines.append(line)
        if chooser and n % 25 == 0:
            rate = (time.monotonic() - started) / n
            print(
                f"  {n:,}/{len(entries):,}  {calls:,} calls, {chooser.hits:,} cached, "
                f"{rate:.1f}s a message"
            )
    with open(out / "manifest.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(line) + "\n" for line in lines)
    how = f"the LLM at {args.llm}, {chooser.identity}" if chooser else "the rules"
    print(
        f"grouped {len(entries):,} message(s) with {how}: "
        f"{outcomes['kept']:,} kept, {outcomes['failed']:,} failed; {calls:,} calls"
    )
    if chooser:
        print(f"  {chooser.hits:,} decisions from the cache, {chooser.misses:,} asked")
    print(f"written to {out}")


# --- grouping by hand ---------------------------------------------------------


def review(args, blobs: Path) -> None:
    """A sheet of labelled messages with two or more PER, ORG or LOC mentions of a class."""
    eligible = []
    for entry in kept(args.manifest):
        if entry["source"] != "human":
            continue
        counts = Counter(c for _, _, c in entry["mask"] if c in DECIDED)
        if any(n >= 2 for n in counts.values()):
            eligible.append(entry)
    chosen = random.Random(args.seed).sample(eligible, min(args.review, len(eligible)))
    path = args.sheet
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            f"# Grouping by hand: {len(chosen)} labelled messages (seed {args.seed})\n\n"
            "Each mention is marked ⟦id CLASS: text⟧. Under each message, write\n"
            "every class's groups on its line: the ids of one entity separated by\n"
            "spaces, the entities by `|`. Every id listed must be used exactly once.\n"
            "Two equal strings can be two entities; group by who or what is meant.\n"
            "Example: `PER: 0 2 5 | 1 | 3 4`\n\n"
        )
        for n, entry in enumerate(chosen, 1):
            text = text_of(blob_path(blobs, entry["checksum"]))
            mentions = [m for m in mentions_of(text, entry["mask"]) if m.cls in DECIDED]
            f.write(f"## {n}. {entry['checksum']}\n\n```\n{tagged(text, mentions)}\n```\n\n")
            for cls in DECIDED:
                ids = [m.id for m in mentions if m.cls == cls]
                # A class with one mention has nothing to decide.
                if len(ids) >= 2:
                    f.write(f"{cls}: \n<!-- {cls} ids: {' '.join(map(str, ids))} -->\n")
            f.write("\n")
    print(f"{len(chosen)} of {len(eligible)} eligible message(s) written to {path}")


def tagged(text: str, mentions: list[Mention]) -> str:
    out, at = [], 0
    for m in mentions:
        if m.start < at:
            continue
        out += [text[at : m.start], f"⟦{m.id} {m.cls}: {m.text}⟧"]
        at = m.end
    return "".join([*out, text[at:]])


def read_sheet(path: Path) -> dict[str, dict[str, list[set[int]]]]:
    """The hand groupings, by checksum then class; refuses a sheet left unfinished."""
    found: dict[str, dict[str, list[set[int]]]] = {}
    checksum = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if heading := re.match(r"## \d+\. ([0-9a-f]{64})", line):
            checksum = heading.group(1)
            found[checksum] = {}
        elif checksum and (row := re.match(r"(PER|ORG|LOC): ?(.*)$", line)):
            cls, groups = row.group(1), row.group(2).strip()
            if not groups:
                sys.exit(f"{path}: {checksum[:12]} has no {cls} groups yet")
            found[checksum][cls] = [set(map(int, g.split())) for g in groups.split("|")]
    return found


# --- scoring -----------------------------------------------------------------


def links(groups: list[set[int]]) -> set[tuple[int, int]]:
    return {pair for g in groups for pair in combinations(sorted(g), 2)}


def score(args, blobs: Path) -> None:
    truth = read_sheet(args.score)
    by_checksum = {e["checksum"]: e for e in kept(args.manifest)}
    approaches = [("rules", None)]
    if args.llm:
        approaches.append(("LLM, thinking", chooser_for(args.llm)))
        approaches.append(("LLM, no thinking", chooser_for(args.llm, think=False)))
    print(f"{len(truth)} message(s) grouped by hand\n")
    print(f"{'':16} {'class':5} {'precision':>9} {'recall':>7} {'F1':>6} {'exact':>6} {'links':>6}")
    for name, chooser in approaches:
        tally: dict[str, Counter] = {cls: Counter() for cls in DECIDED}
        for checksum, wanted in truth.items():
            entry = by_checksum[checksum]
            text = text_of(blob_path(blobs, checksum))
            mentions = mentions_of(text, entry["mask"])
            got = group_message(text, mentions, chooser).entities
            for cls, groups in wanted.items():
                ids = {i for g in groups for i in g}
                expected = {m.id for m in mentions if m.cls == cls}
                if ids != expected:
                    sys.exit(f"{checksum[:12]} {cls}: the ids must be {sorted(expected)}")
                made = [{m.id for m in e.mentions} for e in got if e.cls == cls]
                true_links, made_links = links(groups), links(made)
                t = tally[cls]
                t["tp"] += len(true_links & made_links)
                t["fp"] += len(made_links - true_links)
                t["fn"] += len(true_links - made_links)
                t["messages"] += 1
                t["exact"] += sorted(map(sorted, made)) == sorted(map(sorted, groups))
        for cls, t in tally.items():
            if not t["messages"]:
                continue
            p = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else 1.0
            r = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else 1.0
            f1 = 2 * p * r / (p + r) if p + r else 0.0
            print(
                f"{name:16} {cls:5} {p:9.2f} {r:7.2f} {f1:6.2f} "
                f"{t['exact'] / t['messages']:6.0%} {t['tp'] + t['fn']:6}"
            )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=Path("anonymised/manifest.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("anonymised-indexed"))
    parser.add_argument("--llm", help="A llama.cpp server, host:port; without it the rules group")
    parser.add_argument(
        "--no-think", action="store_true", help="Ask a reasoning model to answer straight away"
    )
    parser.add_argument("--limit", type=int, default=None, help="Only this many, for a trial run")
    parser.add_argument("--review", type=int, help="Write a sheet of this many to group by hand")
    parser.add_argument("--sheet", type=Path, default=Path("notes/grouping-review.md"))
    parser.add_argument("--score", type=Path, help="A sheet grouped by hand, to score against")
    parser.add_argument("--seed", type=int, default=0, help="Seeds the review sample")
    args = parser.parse_args(argv)
    blobs = blobs_dir()
    if args.review:
        review(args, blobs)
    elif args.score:
        score(args, blobs)
    else:
        run(args, blobs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
