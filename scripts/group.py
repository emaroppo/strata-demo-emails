"""Group the anonymised set's masked spans into entities, and number them.

    uv run python scripts/group.py [--llm http://host:port] [--limit N]
    uv run python scripts/group.py --review 40          # a sheet to group by hand
    uv run python scripts/group.py --score notes/grouping-review.md [--llm URL]

Reads ``anonymised/manifest.jsonl`` (written by ``anonymise.py``) for the
kept messages and the spans each was masked with. Without ``--llm`` the
rules group them, the baseline; with it, PER, ORG and LOC mentions go one
by one to that llama.cpp server. Written under ``--out``, gitignored like
``anonymised/``: each message with ``[PER_1]``-style placeholders, and a
manifest saying per message what was found, how many calls it took,
whether it was kept, and each span with the entity it went into. A
message the chooser can't answer for is dropped. What ``anonymise.py
--cut`` left out of a message is left out here too.

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

from anonymise import BlobFiles, rendered, text_of
from group_entities import Entity, GroupingFailed, Mention, group_message, numbered
from group_entities.cache import CachedChooser
from group_entities.llm import LlamaCppChooser
from group_entities.loop import DECIDED

from strata.catalog.config import open_catalog
from strata.project import Project, Settings

CACHE = Path(".state/grouping/decisions.jsonl")


def blob_files() -> BlobFiles:
    project = Project.load(Path("."))
    config = Settings.load(None).catalogs.named(project.catalog.name)
    # Refuses early if the catalog isn't this project's
    return BlobFiles(open_catalog(config))


def kept(manifest: Path) -> list[dict]:
    entries = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    entries = [e for e in entries if e["kept"]]
    if entries and "mask" not in entries[0]:
        sys.exit(f"{manifest} has no spans: rerun scripts/anonymise.py, which now records them")
    return entries


def mentions_of(text: str, mask: list) -> list[Mention]:
    spans = sorted((s, e, c) for s, e, c in mask)
    return [Mention(i, s, e, c, text[s:e]) for i, (s, e, c) in enumerate(spans)]


def decisions(mentions: list[Mention]) -> int:
    """What grouping a message will ask: every mention of a decided class but its first."""
    counts = Counter(m.cls for m in mentions if m.cls in DECIDED)
    return sum(n - 1 for n in counts.values())


def partition(entities: list[Entity]) -> list[list[int]]:
    """The decided classes' groups, as mention ids, comparable across groupers."""
    return sorted(sorted(m.id for m in e.mentions) for e in entities if e.cls in DECIDED)


def chooser_for(url: str | None, think: bool = True) -> CachedChooser | None:
    if url is None:
        return None
    return CachedChooser(LlamaCppChooser(url if "://" in url else f"http://{url}", think), CACHE)


# --- the run ---------------------------------------------------------------


def group_one(
    entry: dict, files: BlobFiles, chooser: CachedChooser | None, cap: int | None, out: Path
) -> dict:
    """One message grouped: its manifest line, and its text written if kept.

    The line carries each span with the entity it was put in (``PER_1``),
    the offsets being into the original text, so replacement can put the
    same value wherever one entity is mentioned.
    """
    text = text_of(files.path(entry["checksum"]))
    mentions = mentions_of(text, entry["mask"])
    line = {"checksum": entry["checksum"], "source": entry["source"]}
    asks = decisions(mentions)
    if cap is not None and entry["source"] != "human" and asks > cap:
        return line | {
            "kept": False,
            "reason": f"{asks} decisions, over --max-decisions",
            "_outcome": "skipped",
        }
    try:
        grouped = group_message(text, mentions, chooser)
    except GroupingFailed as e:
        return line | {"kept": False, "reason": str(e), "_outcome": "failed"}
    names = numbered(grouped.entities)
    line |= {
        "kept": True,
        "entities": dict(sorted(Counter(e.cls for e in grouped.entities).items())),
        "calls": grouped.calls,
        "_outcome": "kept",
    }
    if chooser:
        # The output check: where the rules group differently, the LLM may
        # have merged two entities, so the message can be left out of what
        # is trained on.
        rules = group_message(text, mentions, None).entities
        line["rules_agree"] = partition(grouped.entities) == partition(rules)
    line["spans"] = [
        {"start": m.start, "end": m.end, "class": m.cls, "entity": names[m.id], "text": m.text}
        for m in mentions
    ]
    cut = [tuple(s) for s in entry.get("cut", [])]
    if cut:
        line["cut"] = entry["cut"]
    # As group_entities.indexed puts them, with the cut left out
    swaps = [(m.start, m.end, f"[{names[m.id]}]") for e in grouped.entities for m in e.mentions]
    (out / "texts" / f"{entry['checksum']}.txt").write_text(
        rendered(text, swaps, cut), encoding="utf-8"
    )
    return line


def run(args, files: BlobFiles) -> None:
    entries = kept(args.manifest)[: args.limit]
    files.fetch(e["checksum"] for e in entries)
    chooser = chooser_for(args.llm, think=not args.no_think)
    out = args.out
    (out / "texts").mkdir(parents=True, exist_ok=True)
    outcomes, calls = Counter(), 0
    started = time.monotonic()
    # Written as it goes, so an interrupted run keeps what it did; a rerun
    # rewrites it whole, the decisions made so far coming from the cache.
    with open(out / "manifest.jsonl", "w", encoding="utf-8") as manifest:
        for n, entry in enumerate(entries, 1):
            line = group_one(entry, files, chooser, args.max_decisions, out)
            outcomes[line.pop("_outcome")] += 1
            if "rules_agree" in line:
                outcomes["rules agree" if line["rules_agree"] else "rules differ"] += 1
            calls += line.get("calls", 0)
            manifest.write(json.dumps(line, ensure_ascii=False) + "\n")
            manifest.flush()
            if chooser and n % 25 == 0:
                rate = (time.monotonic() - started) / n
                print(
                    f"  {n:,}/{len(entries):,}  {calls:,} calls, {chooser.hits:,} cached, "
                    f"{rate:.1f}s a message"
                )
    how = f"the LLM at {args.llm}, {chooser.identity}" if chooser else "the rules"
    print(
        f"grouped {len(entries):,} message(s) with {how}: "
        f"{outcomes['kept']:,} kept, {outcomes['failed']:,} failed, "
        f"{outcomes['skipped']:,} skipped; {calls:,} calls"
    )
    if chooser:
        print(f"  {chooser.hits:,} decisions from the cache, {chooser.misses:,} asked")
        print(
            f"  the rules group {outcomes['rules agree']:,} the same way and "
            f"{outcomes['rules differ']:,} differently (rules_agree in the manifest)"
        )
    print(f"written to {out}")


# --- grouping by hand ---------------------------------------------------------


def review(args, files: BlobFiles) -> None:
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
            text = text_of(files.path(entry["checksum"]))
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


def score(args, files: BlobFiles) -> None:
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
            text = text_of(files.path(checksum))
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
    parser.add_argument(
        "--max-decisions",
        type=int,
        help="Skip a message needing more decisions than this, unless labelled by hand",
    )
    parser.add_argument("--review", type=int, help="Write a sheet of this many to group by hand")
    parser.add_argument("--sheet", type=Path, default=Path("notes/grouping-review.md"))
    parser.add_argument("--score", type=Path, help="A sheet grouped by hand, to score against")
    parser.add_argument("--seed", type=int, default=0, help="Seeds the review sample")
    args = parser.parse_args(argv)
    files = blob_files()
    if args.review:
        review(args, files)
    elif args.score:
        score(args, files)
    else:
        run(args, files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
