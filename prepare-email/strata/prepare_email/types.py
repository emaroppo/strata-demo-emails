"""What the catalog stores when the corpus is mail.

One sample is one message *body*, as characters. Two decisions worth
stating, because both are visible for the life of the corpus.

**Headers are metadata, not text.** A span is a pair of character offsets
into the sample, so anything prepended to the body shifts every annotation
made against it. From, subject and date are recorded on the sample instead,
where they can be read, queried and shown without moving a single offset.

**Threads are not grouped yet.** Messages quoting each other are
near-duplicates, and near-duplicates on both sides of a train/val split make
the score meaningless — the same reason frames of one video move together.
The hook is inherited and the prepared index can already declare a group;
what is missing is a rule for deciding which messages are one thread, and
that is a decision about a corpus rather than about mail.
"""

from typing import ClassVar

from strata.catalog.builtin_types import Text


class Email(Text):
    """A message body, stored as a document."""

    segment: ClassVar[str] = "email"
