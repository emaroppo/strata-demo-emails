"""The chooser: one decision per mention, an entity so far or a new one."""

import json
from typing import Protocol

import httpx

from .mentions import Entity, Mention

#: Changes whenever the prompt or the reply's shape does, so cached
#: decisions made under another prompt are not reused.
PROMPT_VERSION = "2"

DESCRIPTIONS = {
    "PER": "a person",
    "ORG": "an organisation: a company, campaign, party, agency, school, publication or list",
    "LOC": "a place: a country, state, city, address, venue, building or room",
}

SYSTEM = """\
You decide which mentions in an email name the same entity.

Every mention below has already been identified as {what}; don't
second-guess that, only decide which ones are the same.

In the email, mentions already decided are tagged with their entity, as
⟦E1: text⟧. The mention to decide now is marked ⟪text⟫.

Answer whether it refers to one of the entities listed, or to a new one.
The same words can name two different entities (two people called Sam, a
father and son with one surname), and different words can name one: a
full name, a surname, a first name, a title with the surname, a nickname,
or initials ("Maria Lopez", "Lopez", "Senator Lopez" and "ML" can all be
one person). Decide from the context. Reply with JSON: a short reason,
then the choice."""


class InvalidChoice(ValueError):
    """The reply was not one of the choices offered."""


class Chooser(Protocol):
    #: What, besides the inputs, the decision depends on: the prompt and model.
    identity: str

    def choose(self, text: str, mention: Mention, entities: list[Entity]) -> int | None:
        """The index into ``entities`` the mention belongs to, or None for a new one."""
        ...


def choices(entities: list[Entity]) -> list[str]:
    return [f"E{i}" for i in range(1, len(entities) + 1)] + ["new"]


def marked(text: str, mention: Mention, entities: list[Entity]) -> str:
    """The email with decided mentions tagged and the current one marked."""
    tags = [
        (m.start, m.end, f"⟦E{i}: {text[m.start : m.end]}⟧")
        for i, e in enumerate(entities, 1)
        for m in e.mentions
    ]
    tags.append((mention.start, mention.end, f"⟪{text[mention.start : mention.end]}⟫"))
    out, at = [], 0
    for start, end, tag in sorted(tags):
        if start < at:
            continue
        out += [text[at:start], tag]
        at = end
    return "".join([*out, text[at:]])


def prompt(text: str, mention: Mention, entities: list[Entity]) -> list[dict]:
    listed = "\n".join(
        f"E{i}: " + ", ".join(dict.fromkeys(f'"{m.text}"' for m in e.mentions))
        for i, e in enumerate(entities, 1)
    )
    return [
        {"role": "system", "content": SYSTEM.format(what=DESCRIPTIONS[mention.cls])},
        {
            "role": "user",
            "content": f"Email:\n\n{marked(text, mention, entities)}\n\n"
            f"Entities so far:\n{listed}\n\n"
            f"Which does ⟪{mention.text}⟫ refer to? One of {', '.join(choices(entities))}.",
        },
    ]


def reply_schema(entities: list[Entity]) -> dict:
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "maxLength": 300},
            "choice": {"enum": choices(entities)},
        },
        "required": ["reason", "choice"],
        "additionalProperties": False,
    }


def parse(reply: str, entities: list[Entity]) -> int | None:
    try:
        choice = json.loads(reply)["choice"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise InvalidChoice(f"Not a reply: {reply[:200]!r}") from e
    if choice == "new":
        return None
    if choice not in choices(entities):
        raise InvalidChoice(f"Not one of the choices: {choice!r}")
    return int(choice[1:]) - 1


class LlamaCppChooser:
    """Asks a llama.cpp server, with the reply constrained to the choices.

    ``url`` is the server's root (``http://host:8080``); it speaks the
    OpenAI-compatible API, and the JSON schema in ``response_format``
    becomes a grammar, so the reply can only name an offered choice.

    ``think=False`` asks a reasoning model to answer straight away
    (``enable_thinking`` in the chat template): many times faster, and
    whether it costs accuracy is for the hand-grouped messages to say.
    """

    def __init__(
        self,
        url: str,
        think: bool = True,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.think = think
        self.client = httpx.Client(base_url=url.rstrip("/"), timeout=timeout, transport=transport)
        self.model = self.client.get("/v1/models").raise_for_status().json()["data"][0]["id"]
        # The file's name, not its path: the path says whose machine it is.
        self.identity = f"prompt {PROMPT_VERSION}, {self.model.rsplit('/', 1)[-1]}" + (
            "" if think else ", no thinking"
        )
        self.last_reason = ""

    def choose(self, text: str, mention: Mention, entities: list[Entity]) -> int | None:
        response = self.client.post(
            "/v1/chat/completions",
            json={
                "model": self.model,
                "messages": prompt(text, mention, entities),
                "temperature": 0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "choice", "schema": reply_schema(entities)},
                },
                **({} if self.think else {"chat_template_kwargs": {"enable_thinking": False}}),
            },
        ).raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        choice = parse(reply, entities)
        self.last_reason = json.loads(reply).get("reason", "")
        return choice
