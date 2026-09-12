"""What the catalog stores when the corpus is mail.

One sample is one message body, as characters; headers are metadata, so
no offset moves. Threads are not grouped yet. See ``docs/adr/0010``.
"""

from typing import ClassVar

from strata.catalog.types.builtin_types import Text


class Email(Text):
    """A message body, stored as a document."""

    segment: ClassVar[str] = "email"
