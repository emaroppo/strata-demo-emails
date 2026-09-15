"""A corpus of pre-parsed messages, as JSON, into documents and candidate spans.

The shape this reads is one a mail corpus is commonly handed over in: a list
of records, each holding messages, each message a body, some headers and
whatever entity extraction had already been run over it.

**The spans it carries are candidates.** They travel in the prepared index,
and landing them is a separate step under a source of its own
(``docs/adr/0028``).

**Offsets are remapped, not trusted.** Each span is moved through the same
transformation as the text and checked against its own text; anything that
no longer slices to what it claims is dropped and counted
(``docs/adr/0033``).
"""

import json
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from strata.catalog.types.preparers import Prepared, Preparer
from strata.labels import Span, Spans

from ._writing import write_document

#: Messages longer than this are not converted. An arbitrary limit, and a
#: first-pass compromise: a number chosen at conversion decides what the
#: durable asset holds, the reverse of the architecture's stance. The
#: source is kept, so raising it is a re-run rather than a loss
#: (``docs/adr/0033``).
DEFAULT_MAX_CHARS = 4000


class MessagesPreparer(Preparer):
    """One JSON corpus into one document per message."""

    name: ClassVar[str] = "email-json"
    produces: ClassVar[str] = "email"
    sources: ClassVar[frozenset[str]] = frozenset({"json"})

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS):
        self.max_chars = max_chars
        self._counts: Counter = Counter()

    def report(self) -> dict[str, int]:
        return dict(self._counts)

    def prepare(self, source: Path, out_dir: Path) -> Iterable[Prepared]:
        records = json.loads(Path(source).read_text(encoding="utf-8"))
        for record in records:
            for message in record.get("messages", []):
                prepared = self._one(record, message, out_dir)
                if prepared is not None:
                    yield prepared

    # ------------------------------------------------------------------

    def _one(self, record: dict, message: dict, out_dir: Path) -> Prepared | None:
        body = message.get("body") or ""
        if not body.strip():
            self._counts["skipped_empty"] += 1
            return None
        if len(body) > self.max_chars:
            self._counts["skipped_oversized"] += 1
            return None

        text, where = _remapped(body)
        spans = self._spans(message, body, text, where)
        headers = message.get("headers") or {}
        metadata = {
            # The join key for the same mail ingested in another format.
            # docs/adr/0010
            "message_id": headers.get("Message-ID") or headers.get("Message-Id") or "",
            "subject": headers.get("Subject") or "",
            "from": headers.get("From") or "",
            "date": headers.get("Date") or "",
            "source_file": record.get("file_path", ""),
            "is_html": bool(message.get("is_html")),
        }
        self._counts["written"] += 1
        return write_document(
            out_dir,
            Path(record.get("file_path") or "message").stem,
            text,
            metadata,
            value=Spans(values=spans) if spans else Spans(),
        )

    def _spans(self, message: dict, body: str, text: str, where: list[int]) -> list[Span]:
        """Every candidate span that still slices to its own text."""
        found: list[Span] = []
        entities = (message.get("entities") or {}).get("manual") or {}
        for label, items in entities.items():
            for item in items or []:
                if not (isinstance(item, list) and len(item) == 3):
                    self._counts["dropped_malformed"] += 1
                    continue
                claimed, start, end = item
                if not (isinstance(start, int) and isinstance(end, int)):
                    self._counts["dropped_malformed"] += 1
                    continue
                if start < 0 or end > len(body) or start >= end:
                    self._counts["dropped_out_of_range"] += 1
                    continue
                if body[start:end] != claimed:
                    # Not a fact about this document
                    self._counts["dropped_mismatched"] += 1
                    continue

                moved_start, moved_end = where[start], where[end]
                wanted = _canonical(str(claimed))
                if text[moved_start:moved_end] != wanted:
                    # Survived the source and not the mapping: dropped rather
                    # than stored askew. docs/adr/0033
                    self._counts["dropped_unmappable"] += 1
                    continue
                found.append(Span(labels=[label], start=moved_start, end=moved_end, text=wanted))
                self._counts[f"span_{label}"] += 1
        return sorted(found, key=lambda s: (s.start, s.end))


def _canonical(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def _remapped(body: str) -> tuple[str, list[int]]:
    """The body as it will be stored, and where each character moved to.

    One entry per character plus one for the end, so a span's start and end
    are both looked up rather than one being derived from a length that the
    transformation may have changed.
    """
    out: list[str] = []
    where = [0] * (len(body) + 1)
    for i, char in enumerate(body):
        where[i] = len(out)
        if char == "﻿":
            continue
        if char == "\r":
            # A CRLF pair keeps only the LF, which the next iteration
            # emits; a lone CR becomes one
            if i + 1 < len(body) and body[i + 1] == "\n":
                continue
            out.append("\n")
            continue
        out.append(char)
    where[len(body)] = len(out)

    stepped = "".join(out)
    composed = unicodedata.normalize("NFC", stepped)
    if composed != stepped:
        # Composition can change lengths, and no per-character map survives
        # it. Every span is checked against its own text afterwards, so
        # anything this moved is dropped rather than stored wrong.
        return composed, where
    return stepped, where
