"""What both conversions share: how a document is named and written.

Names are content-addressed, with a readable stem in front: stable, so the
same message always writes the same filename with the same bytes
(``docs/adr/0033``), and unique, so two mailboxes both holding
``inbox.eml`` do not have the second overwrite the first.
"""

import hashlib
import re
from pathlib import Path

from strata.catalog.types.preparers import Prepared

from .types import Email

#: Long enough that a collision needs billions of documents, short enough
#: that a human can still read the stem in front of it.
DIGEST_CHARS = 12


def canonical(text: str) -> bytes:
    """The bytes to write: UTF-8, LF endings, NFC, no BOM.

    Canonical here rather than at ingest. See ``docs/adr/0033``.
    """
    return Email().canonicalise(text.encode("utf-8"))


def write_document(out_dir: Path, stem: str, text: str, metadata: dict, value=None) -> Prepared:
    """One document, named for what it says rather than where it sat."""
    data = canonical(text)
    digest = hashlib.sha256(data).hexdigest()[:DIGEST_CHARS]
    path = Path(out_dir) / f"{_readable(stem)}-{digest}.txt"
    path.write_bytes(data)
    return Prepared(
        path=path,
        metadata={**metadata, "characters": len(data.decode("utf-8"))},
        value=value,
    )


def _readable(stem: str) -> str:
    """A filename fragment that survives every filesystem, still legible."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    # Trailing rather than leading: what distinguishes two long mailbox
    # paths is almost always at the end of them.
    return cleaned[-60:] or "message"
