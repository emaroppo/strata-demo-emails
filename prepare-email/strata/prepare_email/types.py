"""What a catalog takes when the corpus is mail.

One sample is one message body, as characters; headers are metadata, so
no offset moves. Threads are not grouped yet. See ``docs/adr/0010``.
"""

from typing import Any, ClassVar

from strata.contracts import Text

from .html import structural_tags


class Email(Text):
    """A message body, stored as a document."""

    segment: ClassVar[str] = "email"

    def facts(self, data: bytes) -> dict[str, Any]:
        """Its length, in characters and in words, and how much HTML it holds.

        Words are split on whitespace, as phishnet counted them. HTML is a
        count of structural tags rather than a yes or no, so a freeze can
        choose its own threshold (strata's ``docs/adr/0049``).
        """
        text = data.decode("utf-8")
        return {
            "characters": len(text),
            "word_count": len(text.split()),
            "html_tags": structural_tags(text),
        }
