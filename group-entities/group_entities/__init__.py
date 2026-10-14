"""Which masked spans in a message are the same entity.

Each class is grouped on its own. PER, ORG and LOC go mention by mention
through a chooser, a local LLM that picks one of the entities so far or a
new one; the rest are grouped by exact match, since an address or a phone
number is its own identity. Code numbers the entities by first appearance
and renders ``[PER_1]``-style placeholders. ``docs/entity-grouping.md``
says why.
"""

from .index import indexed, numbered
from .loop import GroupingFailed, group_message
from .mentions import Entity, Mention

__all__ = ["Entity", "GroupingFailed", "Mention", "group_message", "indexed", "numbered"]
