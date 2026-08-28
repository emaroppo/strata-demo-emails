"""What both conversions share: how a document is named and written.

Names are content-addressed, with a readable stem in front. Two properties
matter and neither is cosmetic.

*Stable.* Converting the same message twice writes the same filename with
the same bytes, so re-running over a source directory that has grown leaves
everything already catalogued exactly where it was. A name carrying a
position in a corpus does not have that property: one message inserted
renames everything after it, and every renamed file re-ingests as a new
sample with no annotations.

*Unique.* Two mailboxes both holding ``inbox.eml`` write different
documents, and a name derived from the source alone would have the second
silently overwrite the first.
"""

import hashlib
import re
from pathlib import Path

from strata.catalog.preparers import Prepared

from .types import Email

#: Long enough that a collision needs billions of documents, short enough
#: that a human can still read the stem in front of it.
DIGEST_CHARS = 12


def canonical(text: str) -> bytes:
    """The bytes to write: UTF-8, LF endings, NFC, no BOM.

    Canonical here rather than at ingest, so the file on disk and the sample
    in the catalog have the same checksum — otherwise the corpus no longer
    says what was catalogued.
    """
    return Email().canonicalise(text.encode("utf-8"))


def write_document(
    out_dir: Path, stem: str, text: str, metadata: dict, value=None, group_id=None
) -> Prepared:
    """One document, named for what it says rather than where it sat."""
    data = canonical(text)
    digest = hashlib.sha256(data).hexdigest()[:DIGEST_CHARS]
    path = Path(out_dir) / f"{_readable(stem)}-{digest}.txt"
    path.write_bytes(data)
    return Prepared(
        path=path,
        metadata={**metadata, "characters": len(data.decode("utf-8"))},
        group_id=group_id,
        value=value,
    )


def _readable(stem: str) -> str:
    """A filename fragment that survives every filesystem, still legible."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    # Trailing rather than leading: what distinguishes two long mailbox
    # paths is almost always at the end of them.
    return cleaned[-60:] or "message"
