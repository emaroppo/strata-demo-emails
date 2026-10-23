"""Mail as preparation stages, and what the email type says about its bytes.

Every message here is made up, addressed at example.org: the repository is
public, and no real mail goes into its tests.
"""

import json
from pathlib import Path

import pytest

from strata.prepare.chain import (
    Chain,
    Counts,
    Drop,
    Emptied,
    Input,
    Item,
    Produced,
    Spec,
    run_chain,
)
from strata.prepare_email.stages import (
    CleanDebris,
    MessageJsonParams,
    ParseMessageJson,
    ParseRfc822,
)
from strata.prepare_email.types import Email

SOURCE = Input(checksum="0" * 64, path=Path("unused"))

MESSAGE = b"""Received: from a.example.org\r
Received: from b.example.org\r
From: Ada <ada@example.org>\r
To: Bob <bob@example.org>\r
Subject: The engine\r
X-Folder: \\Ada_Dec2000\\Notes Folders\\Sent\r
Content-Type: text/plain; charset="us-ascii"\r
Content-Transfer-Encoding: 7bit\r
\r
Dear Bob,=\r
 the engine runs.=20\r
\r
> quoted reply\r
"""

MULTIPART = b"""From: Ada <ada@example.org>\r
Subject: Both\r
MIME-Version: 1.0\r
Content-Type: multipart/alternative; boundary="b"\r
\r
--b\r
Content-Type: text/html\r
\r
<html><body><p>Page</p></body></html>\r
--b\r
Content-Type: text/plain\r
\r
Plain words.\r
--b--\r
"""


def parse(raw: bytes) -> Item | Drop:
    return ParseRfc822().keep(Item(raw), SOURCE)


def document(*messages: dict) -> bytes:
    return json.dumps({"file_path": "x/00000001.eml", "messages": list(messages)}).encode()


# ----------------------------------------------------------------------
# parse-rfc822
# ----------------------------------------------------------------------


def test_every_header_is_kept_by_its_name_in_lower_case():
    item = parse(MESSAGE)
    assert isinstance(item, Item)
    assert item.facts["subject"] == "The engine"
    assert item.facts["x-folder"] == "\\Ada_Dec2000\\Notes Folders\\Sent"
    assert item.facts["received"] == ["from a.example.org", "from b.example.org"]


def test_the_body_is_the_plain_text_part_and_no_other():
    item = parse(MULTIPART)
    assert isinstance(item, Item)
    assert item.body.decode().strip() == "Plain words."


def test_a_message_with_no_plain_part_is_dropped():
    html_only = MULTIPART.replace(b"--b\r\nContent-Type: text/plain\r\n\r\nPlain words.\r\n", b"")
    assert parse(html_only) == Drop("no_plain_part")


def test_a_message_with_an_empty_body_is_dropped():
    assert parse(b"Subject: nothing\r\n\r\n  \r\n") == Drop("empty_body")


def test_bytes_no_charset_explains_become_replacement_characters():
    item = parse(b"Subject: caf\xe9\r\n\r\nna\xefve\r\n")
    assert isinstance(item, Item)
    json.dumps(item.facts)  # writable as JSON, which a lone surrogate is not
    assert "�" in item.facts["subject"]
    assert item.body.decode("utf-8")


# ----------------------------------------------------------------------
# parse-message-json
# ----------------------------------------------------------------------


def test_a_document_of_one_message_gives_its_body_and_headers():
    raw = document({"headers": {"Subject": "Hi", "From": "ada@example.org"}, "body": "Hello."})
    item = ParseMessageJson().keep(Item(raw), SOURCE)
    assert isinstance(item, Item)
    assert item.body == b"Hello."
    assert item.facts == {"subject": "Hi", "from": "ada@example.org"}


def test_a_document_of_several_messages_waits_for_a_thread_model():
    raw = document({"body": "one"}, {"body": "two"})
    assert ParseMessageJson().keep(Item(raw), SOURCE) == Drop("several_messages")


def test_boilerplate_cut_from_the_body_is_put_back_where_it_was_kept():
    raw = document({"body": "Hello.\n", "disclaimers": ["Confidential."], "footers": ["-- \nAda"]})
    item = ParseMessageJson().keep(Item(raw), SOURCE)
    assert isinstance(item, Item)
    assert item.body == b"Hello.\n\nConfidential.\n\n-- \nAda"

    as_kept = ParseMessageJson(MessageJsonParams(restore_boilerplate=False)).keep(Item(raw), SOURCE)
    assert isinstance(as_kept, Item)
    assert as_kept.body == b"Hello.\n"


# ----------------------------------------------------------------------
# clean-debris, and the chain
# ----------------------------------------------------------------------


def test_cleaning_changes_the_body_and_keeps_the_facts():
    item = CleanDebris().transform(
        Item(b"Dear Bob,=\r\n the engine=20\r\n> quoted", {"a": 1}), SOURCE
    )
    assert item.body == b"Dear Bob, the engine\nquoted"
    assert item.facts == {"a": 1}


def test_a_maildir_chain_runs_from_the_installed_stages(tmp_path):
    spec = Spec.from_toml(
        'name = "trial"\n[[stage]]\nname = "parse-rfc822"\n[[stage]]\nname = "clean-debris"\n'
        '[output]\ncollection = "mail/single"\ntype = "email"\n'
    )
    chain = Chain.load(spec)
    path = tmp_path / ("a" * 64)
    path.write_bytes(MESSAGE)
    empty = tmp_path / ("b" * 64)
    empty.write_bytes(b"Subject: nothing\r\n\r\n")
    counts = Counts()
    found = list(run_chain(chain, [Input("a" * 64, path), Input("b" * 64, empty)], counts))
    [produced, emptied] = found
    assert isinstance(produced, Produced)
    assert produced.body == b"Dear Bob, the engine runs.\n\nquoted reply"
    assert produced.facts["subject"] == "The engine"
    assert emptied == Emptied("b" * 64, "parse-rfc822", "empty_body")
    assert counts.balanced()


# ----------------------------------------------------------------------
# What the type computes from the bytes
# ----------------------------------------------------------------------


def test_the_email_type_counts_characters_words_and_tags():
    facts = Email().facts("Ünïcode words <br> and <p>two</p>\n".encode())
    assert facts == {"characters": 34, "word_count": 5, "html_tags": 2}


@pytest.mark.parametrize("text", ["", "plain words, nothing more"])
def test_text_without_markup_has_no_tags(text):
    assert Email().facts(text.encode())["html_tags"] == 0
