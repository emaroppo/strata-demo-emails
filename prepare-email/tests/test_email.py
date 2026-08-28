"""Mail into the catalog's shape.

The test that matters most here is the one about offsets. A corpus that
arrives with candidate spans arrives with offsets into *its* text, and the
text this stores is canonical — so a document containing CRLF has every
span after the first line ending sitting one character earlier than the
source says. Carried across unmapped it still validates, still trains, and
points at the wrong characters.
"""

import json

import pytest

from strata.catalog.prepared import PreparedIndex
from strata.catalog.preparer_conformance import PreparerContract
from strata.catalog.preparers import PreparerError, run
from strata.prepare_email.eml import EmlPreparer
from strata.prepare_email.messages import MessagesPreparer
from strata.prepare_email.types import Email

MESSAGE = b"""From: Ada <ada@example.org>\r
To: Bob <bob@example.org>\r
Subject: The engine\r
Date: Mon, 3 Jun 1843 09:00:00 +0000\r
Message-ID: <1@example.org>\r
Content-Type: text/plain; charset="utf-8"\r
\r
Dear Bob,\r
\r
Ada Lovelace works at the Analytical Society.\r
"""

BODY = "Dear Bob,\r\n\r\nAda Lovelace works at the Analytical Society.\r\n"


def corpus(body: str = BODY, entities: dict | None = None, path: str = "mail/0001.eml"):
    return [
        {
            "file_path": path,
            "messages": [
                {
                    "body": body,
                    "headers": {
                        "Subject": "The engine",
                        "From": "ada@example.org",
                        "Message-ID": "<1@example.org>",
                    },
                    "entities": {"manual": entities or {}},
                }
            ],
        }
    ]


# ----------------------------------------------------------------------
# The type
# ----------------------------------------------------------------------


def test_mail_is_text_with_a_subtype_of_its_own():
    # A query for text has to keep returning mail, or a corpus disappears
    # from everything that asks for documents
    assert Email.media == "text"
    assert Email.subtype() == "email"


def test_mail_has_the_canonical_form_documents_have():
    assert Email.canonicalises()


# ----------------------------------------------------------------------
# .eml
# ----------------------------------------------------------------------


@pytest.fixture
def mailbox(tmp_path):
    path = tmp_path / "letter.eml"
    path.write_bytes(MESSAGE)
    return path


def test_the_document_is_the_body_alone(mailbox, tmp_path):
    out = tmp_path / "out"
    index = run(EmlPreparer(), [mailbox], out)
    [name] = index.samples
    # Headers prepended would shift every offset annotated against it
    assert (out / name).read_text() == (
        "Dear Bob,\n\nAda Lovelace works at the Analytical Society.\n"
    )


def test_the_headers_are_recorded_on_the_sample(mailbox, tmp_path):
    index = run(EmlPreparer(), [mailbox], tmp_path / "out")
    [entry] = index.samples.values()
    assert entry.metadata["subject"] == "The engine"
    assert entry.metadata["message_id"] == "<1@example.org>"
    assert entry.metadata["from"] == "Ada <ada@example.org>"


def test_a_message_with_no_plain_part_is_refused(tmp_path):
    html = tmp_path / "fancy.eml"
    html.write_bytes(
        b'Subject: Fancy\r\nContent-Type: text/html; charset="utf-8"\r\n\r\n'
        b"<p>Ada Lovelace</p>\r\n"
    )
    # Offsets into markup are not offsets into anything a reviewer reads,
    # and rendering it is a different conversion
    with pytest.raises(PreparerError, match="no plain text part"):
        run(EmlPreparer(), [html], tmp_path / "out")


def test_two_mailboxes_with_one_name_do_not_collide(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    for directory, body in ((first, b"one"), (second, b"two")):
        directory.mkdir()
        (directory / "inbox.eml").write_bytes(
            b'Subject: x\r\nContent-Type: text/plain; charset="utf-8"\r\n\r\n' + body
        )
    out = tmp_path / "out"
    index = run(
        EmlPreparer(), [first / "inbox.eml", second / "inbox.eml"], out
    )
    # A name derived from the source alone would have the second silently
    # overwrite the first
    assert len(index.samples) == 2


# ----------------------------------------------------------------------
# Message JSON, and the offsets it comes with
# ----------------------------------------------------------------------


@pytest.fixture
def source(tmp_path):
    def _write(records) -> "object":
        path = tmp_path / "corpus.json"
        path.write_text(json.dumps(records))
        return path

    return _write


def test_candidate_spans_still_slice_to_their_own_text(source, tmp_path):
    """The whole reason offsets are remapped rather than carried.

    Two CRLFs precede these spans in the source, so both sit two characters
    earlier in the document as stored. Unmapped, they would point at the
    right document and the wrong words.
    """
    records = corpus(
        entities={
            "PER": [["Ada Lovelace", 13, 25]],
            "ORG": [["Analytical Society", 39, 57]],
        }
    )
    out = tmp_path / "out"
    index = run(MessagesPreparer(), [source(records)], out)
    [(name, entry)] = index.samples.items()
    document = (out / name).read_text()

    assert [s.labels for s in entry.value.values] == [["PER"], ["ORG"]]
    for span in entry.value.values:
        assert document[span.start : span.end] == span.text


def test_a_span_that_does_not_slice_to_its_text_is_dropped(source, tmp_path):
    records = corpus(entities={"PER": [["Somebody Else", 0, 13]]})
    preparer = MessagesPreparer()
    index = run(preparer, [source(records)], tmp_path / "out")
    [entry] = index.samples.values()
    assert entry.value.values == []
    # Counted, not silent
    assert preparer.report()["dropped_mismatched"] == 1


def test_a_malformed_span_is_dropped(source, tmp_path):
    records = corpus(entities={"PER": [["Ada", "13", 25], ["Ada"]]})
    preparer = MessagesPreparer()
    run(preparer, [source(records)], tmp_path / "out")
    assert preparer.report()["dropped_malformed"] == 2


def test_a_span_past_the_end_of_the_body_is_dropped(source, tmp_path):
    records = corpus(entities={"PER": [["Ada Lovelace", 13, 9000]]})
    preparer = MessagesPreparer()
    run(preparer, [source(records)], tmp_path / "out")
    assert preparer.report()["dropped_out_of_range"] == 1


def test_an_empty_message_is_skipped_and_counted(source, tmp_path):
    preparer = MessagesPreparer()
    index = run(preparer, [source(corpus(body="   \n"))], tmp_path / "out")
    assert index.samples == {}
    assert preparer.report()["skipped_empty"] == 1


def test_a_message_past_the_cap_is_skipped_and_counted(source, tmp_path):
    preparer = MessagesPreparer(max_chars=10)
    run(preparer, [source(corpus())], tmp_path / "out")
    # A corpus quietly smaller than the file it came from is the failure
    # this whole tree keeps guarding against
    assert preparer.report()["skipped_oversized"] == 1


def test_a_message_with_no_candidates_still_becomes_a_document(source, tmp_path):
    index = run(MessagesPreparer(), [source(corpus())], tmp_path / "out")
    [entry] = index.samples.values()
    assert entry.value.values == []


def test_the_join_key_back_to_the_original_mail_is_kept(source, tmp_path):
    index = run(MessagesPreparer(), [source(corpus())], tmp_path / "out")
    [entry] = index.samples.values()
    # Re-importing the same mail as .eml produces different bytes and so a
    # different sample; this is what would carry review work across
    assert entry.metadata["message_id"] == "<1@example.org>"


def test_the_candidates_survive_the_index_being_written(source, tmp_path):
    records = corpus(entities={"PER": [["Ada Lovelace", 13, 25]]})
    out = tmp_path / "out"
    run(MessagesPreparer(), [source(records)], out)
    back = PreparedIndex.load(out)
    [entry] = back.samples.values()
    assert entry.value.values[0].labels == ["PER"]


# ----------------------------------------------------------------------
# The contract
# ----------------------------------------------------------------------


class TestEmlConforms(PreparerContract):
    @pytest.fixture
    def preparer(self):
        return EmlPreparer()

    @pytest.fixture
    def source(self, tmp_path):
        path = tmp_path / "letter.eml"
        path.write_bytes(MESSAGE)
        return path


class TestMessagesConform(PreparerContract):
    @pytest.fixture
    def preparer(self):
        return MessagesPreparer()

    @pytest.fixture
    def source(self, tmp_path):
        path = tmp_path / "corpus.json"
        path.write_text(json.dumps(corpus(entities={"PER": [["Ada Lovelace", 13, 25]]})))
        return path
