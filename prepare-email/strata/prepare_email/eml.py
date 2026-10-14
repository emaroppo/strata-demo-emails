"""``.eml`` files into message bodies.

The standard library parses mail, so this is thin on purpose. It adds the
two decisions the parser cannot make: the plain text part is the document,
and no other; and a message with no plain part is refused, not skipped.
A plain part that is really HTML source is left out and counted.
See ``docs/adr/0033``.
"""

from collections import Counter
from collections.abc import Iterable
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import ClassVar

from strata.prepare import Prepared, Preparer, PreparerError

from ._writing import write_document
from .html import DEFAULT_MIN_TAGS, looks_like_html

#: Headers worth carrying, and what each is called on the sample: chosen,
#: not kept wholesale. docs/adr/0010
HEADERS: dict[str, str] = {
    "Message-ID": "message_id",
    "Subject": "subject",
    "From": "from",
    "To": "to",
    "Date": "date",
}


class EmlPreparer(Preparer):
    """One ``.eml`` file into one document."""

    name: ClassVar[str] = "eml"
    produces: ClassVar[str] = "email"
    sources: ClassVar[frozenset[str]] = frozenset({"eml"})

    def __init__(self, min_html_tags: int = DEFAULT_MIN_TAGS):
        self.min_html_tags = min_html_tags
        self._counts: Counter = Counter()

    def report(self) -> dict[str, int]:
        return dict(self._counts)

    def prepare(self, source: Path, out_dir: Path, *, root: Path) -> Iterable[Prepared]:
        message = BytesParser(policy=policy.default).parsebytes(Path(source).read_bytes())
        body = message.get_body(preferencelist=("plain",))
        if body is None:
            raise PreparerError(
                f"{Path(source).name} has no plain text part. Its offsets would "
                f"be into HTML source rather than into anything a reviewer "
                f"reads, so rendering it is a conversion of its own — set those "
                f"messages aside, or write a preparer that renders them."
            )

        # Decoded through the part's declared charset. docs/adr/0010
        text = body.get_content()
        if looks_like_html(text, self.min_html_tags):
            self._counts["skipped_html"] += 1
            return
        self._counts["written"] += 1
        metadata = {name: str(message[header] or "") for header, name in HEADERS.items()}
        metadata["source_file"] = Path(source).name
        yield write_document(out_dir, Path(source).stem, text, metadata)
