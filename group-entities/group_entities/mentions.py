"""Mentions, the entities they are grouped into, and what makes two equal."""

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Mention:
    """One detected span: its id within the message, range, class and text."""

    id: int
    start: int
    end: int
    cls: str
    text: str


@dataclass
class Entity:
    """Mentions of one class that refer to the same thing, in reading order."""

    cls: str
    mentions: list[Mention] = field(default_factory=list)


def key(cls: str, text: str) -> str:
    """What two mentions of ``cls`` must share to be the same string.

    Case and runs of whitespace never matter. A phone number is its
    digits, and a URL drops its brackets, scheme, ``www.`` and trailing
    slash, so the same address written two ways is one key.
    """
    text = " ".join(text.split()).casefold()
    if cls == "PHONE":
        return re.sub(r"\D", "", text)
    if cls == "URL":
        text = text.strip("<>[]() ")
        text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
        text = text.removeprefix("www.")
        return text.rstrip("/")
    return text
