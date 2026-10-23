"""Mail as preparation stages: parsed from what a corpus arrives as, then cleaned.

Two ways in, both producing ``email`` items whose body is the message text
as UTF-8 and whose facts are every header the message carried, keyed by
the header's name in lower case. A header that repeats keeps every value,
as a list. Headers are facts about the occurrence, so they go on the origin
(``docs/adr/0049`` in strata); what the text says about itself, its length
and its HTML, the type computes. Then cleaning, which changes the body
and records nothing.

No stage here decides what a project trains on. A body with HTML in it is
kept, and a long one too: leaving them out is a choice made when a dataset
version is frozen (strata's ``docs/adr/0045``). A message with no text to
store is the only one dropped, and it is counted.
"""

import json
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any, ClassVar

from strata.prepare.chain import BYTES, Drop, Filter, Item, StageParams, Transform

from .cleaning import without_debris

EMAIL = "email"


def _text(value: Any) -> str:
    """A header or body as text that will survive being written as JSON.

    The parser keeps undecodable bytes as lone surrogates, which UTF-8
    cannot encode. They become the replacement character instead.
    """
    return str(value).encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _with_header(facts: dict[str, Any], name: str, value: str) -> None:
    key = name.lower()
    if key not in facts:
        facts[key] = value
    elif isinstance(facts[key], list):
        facts[key].append(value)
    else:
        facts[key] = [facts[key], value]


class ParseRfc822(Filter):
    """An RFC 822 message (a maildir file, an ``.eml``) into its plain text and headers.

    The plain text part is the body, and no other. A message with none is
    dropped as ``no_plain_part``, and one whose plain part is empty as
    ``empty_body``. The text is decoded through the part's declared
    charset.
    """

    name: ClassVar[str] = "parse-rfc822"
    version: ClassVar[str] = "1"
    accepts: ClassVar[str] = BYTES
    produces: ClassVar[str] = EMAIL

    def keep(self, item, source):
        message = BytesParser(policy=policy.default).parsebytes(item.body)
        assert isinstance(message, EmailMessage)
        facts: dict[str, Any] = {}
        for name, value in message.items():
            _with_header(facts, name, _text(value))
        part = message.get_body(preferencelist=("plain",))
        if part is None:
            return Drop("no_plain_part")
        assert isinstance(part, EmailMessage)
        text = _text(part.get_content())
        if not text.strip():
            return Drop("empty_body")
        return Item(text.encode("utf-8"), facts)


class MessageJsonParams(StageParams):
    #: Put back disclaimers and footers an earlier pipeline cut from the
    #: body and kept beside it, so the stored text is the message as sent.
    restore_boilerplate: bool = True


class ParseMessageJson(Filter[MessageJsonParams]):
    """A document of pre-parsed messages, as JSON, into its one message.

    The shape phishnet stored: ``{"file_path", "messages": [{"headers",
    "body", ...}]}``. Only a document holding exactly one message is
    taken. One holding several is a thread, which needs a message model
    that says how its messages relate, and is dropped as
    ``several_messages`` until there is one. Labels the document carries
    (entities, sentiment, topic) are not facts about the message, and are
    left for an import run.
    """

    name: ClassVar[str] = "parse-message-json"
    version: ClassVar[str] = "1"
    accepts: ClassVar[str] = BYTES
    produces: ClassVar[str] = EMAIL
    Params = MessageJsonParams

    def keep(self, item, source):
        document = json.loads(item.body)
        messages = document.get("messages") or []
        if len(messages) != 1:
            return Drop("several_messages" if messages else "no_message")
        [message] = messages
        facts: dict[str, Any] = {}
        for name, value in (message.get("headers") or {}).items():
            _with_header(facts, name, _text(value))
        text = message.get("body") or ""
        if self.params.restore_boilerplate:
            kept = [*(message.get("disclaimers") or []), *(message.get("footers") or [])]
            text = "\n\n".join([text.rstrip("\n"), *(_text(k).strip("\n") for k in kept)])
        if not text.strip():
            return Drop("empty_body")
        return Item(_text(text).encode("utf-8"), facts)


class CleanDebris(Transform):
    """Quoted-printable debris, ``[IMAGE]`` placeholders and quote prefixes, removed.

    phishnet's cleaning, so that its corpora can be prepared again from
    their sources and come out as it kept them. See :mod:`.cleaning`.
    """

    name: ClassVar[str] = "clean-debris"
    version: ClassVar[str] = "1"
    accepts: ClassVar[str] = EMAIL
    produces: ClassVar[str] = EMAIL

    def transform(self, item, source):
        return Item(without_debris(item.body.decode("utf-8")).encode("utf-8"), item.facts)


__all__ = ["EMAIL", "CleanDebris", "MessageJsonParams", "ParseMessageJson", "ParseRfc822"]
