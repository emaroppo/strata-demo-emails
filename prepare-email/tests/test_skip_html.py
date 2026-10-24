"""HTML mail skipped in a label set, through an answers file.

Every message here is made up, addressed at example.org.
"""

import json

import pytest

from strata.catalog import Catalog
from strata.contracts import SpanSchema
from strata.prepare_email.skip_html import html_skips, main, rule

PAGE = "<table><tr><td><p>Dear Ada,</p></td></tr></table>\n"
PLAIN = "Dear Ada, the engine runs. <br> once is not a page.\n"


@pytest.fixture
def catalog(tmp_path):
    catalog = Catalog.local(tmp_path / "catalog")
    for name, text, collection in [
        ("page.txt", PAGE, "mail/single"),
        ("plain.txt", PLAIN, "mail/single"),
        ("elsewhere.txt", PAGE.replace("Ada", "Bob"), "mail/other"),
    ]:
        path = tmp_path / name
        path.write_text(text)
        catalog.ingest([path], media="text", collections=[collection])
    catalog.label_sets.create("entities", SpanSchema(classes=["PER"]))
    return catalog


def test_only_pages_in_the_collections_named_are_skipped(catalog):
    answers, read = html_skips(catalog, "entities", ["mail/single"])
    assert read == 2
    [sample] = answers["samples"]
    page = catalog.samples.by_checksum(sample["checksum"])
    assert page is not None
    assert catalog.blobs.get(page.location).decode() == PAGE
    [row] = sample["rows"]
    assert row == {"state": "skipped", "source": "import", "batch": rule(3)}


def test_the_file_carries_the_label_sets_schema_and_names_the_rule(catalog):
    answers, _ = html_skips(catalog, "entities", ["mail/single"], min_tags=1)
    assert answers["schema"]["classes"] == ["PER"]
    assert answers["catalog_id"] == "rules/prepare-email/looks_like_html@min_tags=1"
    assert rule(1) == "prepare-email/looks_like_html@min_tags=1"
    # One stray tag is a page when one tag is enough
    assert len(answers["samples"]) == 2


def test_the_command_writes_the_file(catalog, tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(f'[catalog]\nroot = "{tmp_path / "catalog"}"\n')
    out = tmp_path / "out" / "skips.json"
    args = ["--config", str(config), "--label-set", "entities", "--out", str(out)]
    assert main([*args, "--collection", "mail/single", "--collection", "mail/other"]) == 0
    assert len(json.loads(out.read_text())["samples"]) == 2


def test_a_label_set_that_does_not_exist_is_refused(catalog):
    with pytest.raises(Exception, match="No label set"):
        html_skips(catalog, "nowhere", ["mail/single"])


def test_the_file_imports_as_one_run_and_once(catalog):
    # Where the catalog is new enough to import answers files at all
    transfer = pytest.importorskip("strata.catalog.transfer")
    answers, _ = html_skips(catalog, "entities", ["mail/single", "mail/other"])
    parsed = transfer.AnswersFile.model_validate(answers)
    assert catalog.import_answers(parsed).copied == 2
    again = catalog.import_answers(parsed)
    assert (again.agreed, again.rows) == (2, 0)
