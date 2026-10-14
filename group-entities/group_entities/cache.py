"""Decisions kept on disk, keyed on everything they depend on."""

import hashlib
import json
from pathlib import Path

from .llm import Chooser
from .mentions import Entity, Mention


def decision_key(identity: str, text: str, mention: Mention, entities: list[Entity]) -> str:
    """The text, the mention, the entities offered, and the prompt and model."""
    payload = json.dumps(
        [
            identity,
            text,
            [mention.start, mention.end, mention.cls],
            [[[m.start, m.end] for m in e.mentions] for e in entities],
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class CachedChooser:
    """A chooser whose decisions are appended to a JSONL file and reused.

    Only valid answers are kept: a reply that failed is asked again.
    """

    def __init__(self, inner: Chooser, path: Path):
        self.inner = inner
        self.identity = inner.identity
        self.path = path
        self.hits = self.misses = 0
        self.known: dict[str, int | None] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                self.known[entry["key"]] = entry["choice"]

    def choose(self, text: str, mention: Mention, entities: list[Entity]) -> int | None:
        k = decision_key(self.identity, text, mention, entities)
        if k in self.known:
            self.hits += 1
            return self.known[k]
        self.misses += 1
        choice = self.inner.choose(text, mention, entities)
        self.known[k] = choice
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"key": k, "choice": choice, "reason": getattr(self.inner, "last_reason", "")}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return choice
