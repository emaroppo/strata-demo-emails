"""Grouping by rule: exact match, and the baseline the LLM has to beat."""

import re

from .mentions import Entity, Mention, key

#: Words dropped before comparing names, so "Senator Lopez" meets "Maria Lopez".
TITLES = frozenset({
    "mr", "mrs", "ms", "miss", "dr", "prof", "sen", "senator", "rep", "representative",
    "gov", "governor", "mayor", "sec", "secretary", "ambassador", "president", "chair",
    "chairman", "chairwoman", "judge", "the",
})  # fmt: skip


def group_exact(mentions: list[Mention]) -> list[Entity]:
    """Mentions with equal keys are one entity; for classes whose string is the identity."""
    entities: dict[str, Entity] = {}
    for m in sorted(mentions, key=lambda m: m.start):
        entities.setdefault(key(m.cls, m.text), Entity(m.cls)).mentions.append(m)
    return list(entities.values())


def words(text: str) -> frozenset[str]:
    """A name's words, casefolded, titles and punctuation aside."""
    return frozenset(w for w in re.findall(r"\w+", text.casefold()) if w not in TITLES)


def group_rules(mentions: list[Mention]) -> list[Entity]:
    """The rule-only baseline for PER, ORG and LOC.

    A mention joins the entity holding the same string. Otherwise it joins
    an entity when one's words contain the other's ("Lopez" and "Maria
    Lopez"), if exactly one entity matches that way; with none or several,
    it opens a new one. Every repeated string is merged, so two people
    called "Sam" are one entity: that is what this baseline cannot do.
    """
    entities: list[Entity] = []
    for m in sorted(mentions, key=lambda m: m.start):
        same = [
            e for e in entities if any(key(m.cls, o.text) == key(m.cls, m.text) for o in e.mentions)
        ]
        if same:
            same[0].mentions.append(m)
            continue
        mine = words(m.text)
        near = [
            e
            for e in entities
            if mine
            and any(
                mine <= words(o.text) or words(o.text) <= mine for o in e.mentions if words(o.text)
            )
        ]
        if len(near) == 1:
            near[0].mentions.append(m)
        else:
            entities.append(Entity(m.cls, [m]))
    return entities
