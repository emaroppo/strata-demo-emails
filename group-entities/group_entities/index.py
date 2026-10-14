"""Numbering entities and writing them into the text."""

from .mentions import Entity


def numbered(entities: list[Entity]) -> dict[int, str]:
    """Each mention id's placeholder name, ``PER_1`` and so on.

    Numbered per class, by each entity's first appearance in the text.
    """
    names: dict[int, str] = {}
    by_class: dict[str, int] = {}
    for entity in sorted(entities, key=lambda e: min(m.start for m in e.mentions)):
        by_class[entity.cls] = n = by_class.get(entity.cls, 0) + 1
        for m in entity.mentions:
            names[m.id] = f"{entity.cls}_{n}"
    return names


def indexed(text: str, entities: list[Entity]) -> str:
    """The text with each mention replaced by its entity's placeholder.

    Overlapping mentions are one placeholder, the first's, as in the
    class-only mask.
    """
    names = numbered(entities)
    out, at = [], 0
    for m in sorted((m for e in entities for m in e.mentions), key=lambda m: (m.start, m.end)):
        if m.start < at:
            continue
        out += [text[at : m.start], f"[{names[m.id]}]"]
        at = m.end
    return "".join([*out, text[at:]])
