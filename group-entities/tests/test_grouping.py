"""Grouping, numbering and caching, on invented text with a scripted chooser."""

import json

import httpx
import pytest

from group_entities import GroupingFailed, group_message, indexed, numbered
from group_entities.cache import CachedChooser
from group_entities.llm import InvalidChoice, LlamaCppChooser, marked, parse
from group_entities.mentions import Entity, Mention, key
from group_entities.rules import group_exact, group_rules


def mentions_of(text: str, *found: tuple[str, str]) -> list[Mention]:
    """Mentions of each (class, string), in order, at its next occurrence."""
    out, at = [], 0
    for cls, s in found:
        start = text.index(s, at)
        out.append(Mention(len(out), start, start + len(s), cls, s))
        at = start + len(s)
    return out


class Scripted:
    """Answers from a list, recording what it was asked."""

    identity = "scripted"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked: list[tuple[str, int]] = []

    def choose(self, text, mention, entities):
        self.asked.append((mention.text, len(entities)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def groups(grouped) -> list[list[str]]:
    return [[m.text for m in e.mentions] for e in grouped.entities]


# keys


def test_keys_ignore_case_whitespace_and_url_and_phone_dressing():
    assert key("PER", "Maria  LOPEZ") == key("PER", "maria lopez")
    assert key("PHONE", "(555) 014-2297") == key("PHONE", "555.014.2297")
    assert key("URL", "<https://www.example.org/a/>") == key("URL", "example.org/a")


# rules


def test_exact_grouping_merges_equal_keys_only():
    text = "Write to a@example.org or A@example.org, not b@example.org."
    found = mentions_of(
        text, ("EMAIL", "a@example.org"), ("EMAIL", "A@example.org"), ("EMAIL", "b@example.org")
    )
    assert [[m.id for m in e.mentions] for e in group_exact(found)] == [[0, 1], [2]]


def test_rules_join_a_surname_and_a_title_to_the_full_name():
    text = "Maria Lopez spoke. Lopez said that Senator Lopez would stay. Sam Okafor left."
    found = mentions_of(
        text,
        ("PER", "Maria Lopez"),
        ("PER", "Lopez"),
        ("PER", "Senator Lopez"),
        ("PER", "Sam Okafor"),
    )
    assert [[m.text for m in e.mentions] for e in group_rules(found)] == [
        ["Maria Lopez", "Lopez", "Senator Lopez"],
        ["Sam Okafor"],
    ]


def test_rules_open_a_new_entity_when_a_name_matches_two():
    text = "Maria Lopez and Mark Lopez came; Lopez stayed."
    found = mentions_of(text, ("PER", "Maria Lopez"), ("PER", "Mark Lopez"), ("PER", "Lopez"))
    assert len(group_rules(found)) == 3


def test_rules_merge_every_repeated_string():
    text = "Sam from the office and Sam from the gym."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    assert len(group_rules(found)) == 1


# the loop


def test_the_loop_asks_about_every_mention_after_a_class_s_first():
    text = "Sam called Ruth. Later Sam called again."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Ruth"), ("PER", "Sam"))
    chooser = Scripted(None, 0)
    grouped = group_message(text, found, chooser)
    assert chooser.asked == [("Ruth", 1), ("Sam", 2)]
    assert grouped.calls == 2
    assert groups(grouped) == [["Sam", "Sam"], ["Ruth"]]


def test_the_loop_can_split_two_equal_strings():
    text = "Sam from the office and Sam from the gym."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    grouped = group_message(text, found, Scripted(None))
    assert groups(grouped) == [["Sam"], ["Sam"]]


def test_the_loop_groups_each_class_apart_and_assigns_every_mention():
    text = "Ruth at Acme, ruth@example.org; Acme again, RUTH@example.org, Paris."
    found = mentions_of(
        text,
        ("PER", "Ruth"),
        ("ORG", "Acme"),
        ("EMAIL", "ruth@example.org"),
        ("ORG", "Acme"),
        ("EMAIL", "RUTH@example.org"),
        ("LOC", "Paris"),
    )
    grouped = group_message(text, found, Scripted(0))
    assert sorted(m.id for e in grouped.entities for m in e.mentions) == list(range(len(found)))
    assert all(len({m.cls for m in e.mentions}) == 1 for e in grouped.entities)
    assert grouped.calls == 1  # the second Acme; email by exact match


def test_a_bad_reply_is_asked_again_once_then_fails_the_message():
    text = "Sam and Sam."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    assert groups(group_message(text, found, Scripted(InvalidChoice("x"), 0))) == [["Sam", "Sam"]]
    with pytest.raises(GroupingFailed):
        group_message(text, found, Scripted(InvalidChoice("x"), InvalidChoice("y")))


def test_without_a_chooser_the_rules_decide():
    text = "Maria Lopez and Lopez."
    found = mentions_of(text, ("PER", "Maria Lopez"), ("PER", "Lopez"))
    grouped = group_message(text, found, None)
    assert grouped.calls == 0
    assert groups(grouped) == [["Maria Lopez", "Lopez"]]


# numbering


def test_entities_are_numbered_per_class_by_first_appearance():
    text = "Ruth met Sam at Acme. Sam thanked Ruth."
    found = mentions_of(
        text, ("PER", "Ruth"), ("PER", "Sam"), ("ORG", "Acme"), ("PER", "Sam"), ("PER", "Ruth")
    )
    entities = [
        Entity("PER", [found[1], found[3]]),
        Entity("ORG", [found[2]]),
        Entity("PER", [found[0], found[4]]),
    ]
    assert numbered(entities)[0] == "PER_1"
    assert indexed(text, entities) == "[PER_1] met [PER_2] at [ORG_1]. [PER_2] thanked [PER_1]."


# the chooser


def test_the_prompt_tags_decided_mentions_and_marks_the_current_one():
    text = "Sam met Ruth, and Sam left."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Ruth"), ("PER", "Sam"))
    entities = [Entity("PER", [found[0]]), Entity("PER", [found[1]])]
    assert marked(text, found[2], entities) == "⟦E1: Sam⟧ met ⟦E2: Ruth⟧, and ⟪Sam⟫ left."


def test_a_reply_must_name_an_offered_choice():
    entities = [Entity("PER", [])]
    assert parse('{"reason": "", "choice": "E1"}', entities) == 0
    assert parse('{"reason": "", "choice": "new"}', entities) is None
    for reply in ('{"choice": "E2"}', "not json", '{"reason": "no choice"}'):
        with pytest.raises(InvalidChoice):
            parse(reply, entities)


def test_the_llama_cpp_chooser_constrains_the_reply_to_the_choices():
    sent = []

    def server(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "some-model.gguf"}]})
        sent.append(json.loads(request.content))
        reply = {"reason": "the same person", "choice": "E1"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})

    chooser = LlamaCppChooser("http://gx10:8080/", transport=httpx.MockTransport(server))
    text = "Sam left; Sam came back."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    assert chooser.choose(text, found[1], [Entity("PER", [found[0]])]) == 0
    assert chooser.identity.endswith("some-model.gguf")
    schema = sent[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["choice"]["enum"] == ["E1", "new"]
    assert sent[0]["temperature"] == 0


def test_a_reply_that_times_out_is_retried_once_then_fails_the_message():
    asked = []

    def server(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m.gguf"}]})
        asked.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    chooser = LlamaCppChooser("http://gx10:8080", transport=httpx.MockTransport(server))
    text = "Sam left; Sam came back."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    with pytest.raises(GroupingFailed, match="No reply within"):
        group_message(text, found, chooser)
    assert len(asked) == 2


# the cache


def test_decisions_are_reused_until_the_prompt_or_model_changes(tmp_path):
    text = "Sam and Sam."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    path = tmp_path / "decisions.jsonl"

    first = CachedChooser(Scripted(0), path)
    group_message(text, found, first)
    again = CachedChooser(Scripted(), path)  # would fail if asked
    assert groups(group_message(text, found, again)) == [["Sam", "Sam"]]
    assert (again.hits, again.misses) == (1, 0)

    changed = Scripted(None)
    changed.identity = "another prompt"
    assert groups(group_message(text, found, CachedChooser(changed, path))) == [["Sam"], ["Sam"]]


def test_without_thinking_the_chooser_says_so_and_is_cached_apart():
    sent = []

    def server(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "/home/someone/m.gguf"}]})
        sent.append(json.loads(request.content))
        reply = {"reason": "", "choice": "new"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})

    transport = httpx.MockTransport(server)
    thinking = LlamaCppChooser("http://gx10:8080", transport=transport)
    quick = LlamaCppChooser("http://gx10:8080", think=False, transport=transport)
    text = "Sam and Sam."
    found = mentions_of(text, ("PER", "Sam"), ("PER", "Sam"))
    for chooser in (thinking, quick):
        chooser.choose(text, found[1], [Entity("PER", [found[0]])])
    assert "chat_template_kwargs" not in sent[0]
    assert sent[1]["chat_template_kwargs"] == {"enable_thinking": False}
    assert thinking.identity != quick.identity
    assert "someone" not in thinking.identity
