"""Mail into a catalog.

A sample type saying what the catalog stores — one message body, as
characters — and two conversions into it: individual ``.eml`` files, and the
message JSON a corpus is often handed over as.

Its own distribution, discovered through entry points; the catalog imports
none of it. See ``docs/adr/0010``.
"""

from .types import Email

__all__ = ["Email"]
