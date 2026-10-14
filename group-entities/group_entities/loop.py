"""One message: every mention assigned to an entity of its class."""

from dataclasses import dataclass

from .llm import Chooser, InvalidChoice
from .mentions import Entity, Mention
from .rules import group_exact, group_rules

#: Classes whose equal strings can still be two entities, so each mention
#: is decided on its own. The rest are their own identity.
DECIDED = ("PER", "ORG", "LOC")


class GroupingFailed(RuntimeError):
    """The chooser gave no valid answer twice; the message is dropped."""


@dataclass
class Grouped:
    entities: list[Entity]
    #: Decisions asked of the chooser, retries included.
    calls: int


def group_message(
    text: str, mentions: list[Mention], chooser: Chooser | None, retries: int = 1
) -> Grouped:
    """Group a message's mentions, class by class.

    PER, ORG and LOC go through ``chooser`` one mention at a time, in
    reading order: the first opens an entity, every later one (an exact
    repeat included) is asked about. Without a chooser they are grouped by
    rule, the baseline. Other classes are grouped by exact match.
    """
    entities: list[Entity] = []
    calls = 0
    for cls in sorted({m.cls for m in mentions}):
        mine = sorted((m for m in mentions if m.cls == cls), key=lambda m: m.start)
        if cls not in DECIDED:
            entities += group_exact(mine)
            continue
        if chooser is None:
            entities += group_rules(mine)
            continue
        grouped: list[Entity] = []
        for m in mine:
            if not grouped:
                grouped.append(Entity(cls, [m]))
                continue
            for attempt in range(retries + 1):
                calls += 1
                try:
                    choice = chooser.choose(text, m, grouped)
                    break
                except InvalidChoice as e:
                    if attempt == retries:
                        raise GroupingFailed(f"No valid choice for mention {m.id}: {e}") from e
            if choice is None:
                grouped.append(Entity(cls, [m]))
            else:
                grouped[choice].mentions.append(m)
        entities += grouped
    return Grouped(entities, calls)
