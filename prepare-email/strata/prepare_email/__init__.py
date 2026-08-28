"""Mail into a catalog.

A sample type saying what the catalog stores — one message body, as
characters — and two conversions into it: individual ``.eml`` files, and the
message JSON a corpus is often handed over as.

Its own distribution because that is what a preparer should be. Nothing here
is imported by the catalog; it is discovered through entry points, and a
checkout that has no mail to convert installs none of it.
"""

from .types import Email

__all__ = ["Email"]
