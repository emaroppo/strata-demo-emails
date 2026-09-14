"""``.eml`` files into message bodies.

The standard library parses mail properly — MIME, transfer encodings,
declared charsets — so this is thin on purpose. What it adds is the two
decisions the parser cannot make: which part of a multipart message *is*
the document, and what to do when there is no such part.

**The plain text part, and no other.** A span is a character offset, so the
document has to be the thing a reviewer reads. HTML source is not: its
offsets land in markup, and a model trained on them learns tag names.

**A message with no plain part is refused, not skipped.** Rendering HTML to
text is a conversion in its own right, with its own choices about what a
list or a table becomes, and pretending otherwise here would quietly put a
different kind of document in the corpus. A converter that could do it
properly is a second preparer, not a branch in this one.
"""

from collections.abc import Iterable
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import ClassVar

from strata.catalog.types.preparers import Prepared, Preparer, PreparerError

from ._writing import write_document

#: Headers worth carrying, and what each is called on the sample. Chosen
#: rather than kept wholesale: a header block runs to dozens of routing
#: lines nobody will ever query, and metadata is stored per sample.
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

    def prepare(self, source: Path, out_dir: Path) -> Iterable[Prepared]:
        message = BytesParser(policy=policy.default).parsebytes(Path(source).read_bytes())
        body = message.get_body(preferencelist=("plain",))
        if body is None:
            raise PreparerError(
                f"{Path(source).name} has no plain text part. Its offsets would "
                f"be into HTML source rather than into anything a reviewer "
                f"reads, so rendering it is a conversion of its own — set those "
                f"messages aside, or write a preparer that renders them."
            )

        # Decoded through the part's declared charset, which is exactly the
        # step Text.canonicalise refuses to guess at
        text = body.get_content()
        metadata = {
            name: str(message[header] or "") for header, name in HEADERS.items()
        }
        metadata["source_file"] = Path(source).name
        yield write_document(out_dir, Path(source).stem, text, metadata)
