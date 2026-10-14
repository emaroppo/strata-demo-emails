"""Telling a page from a message that mentions markup."""

import pytest

from strata.prepare_email.html import looks_like_html

PAGE = (
    '<table width="100%"><tr><td><font face="Arial">Dear Ana,</font></td></tr>'
    "<tr><td><p>See you on Tuesday.</p></td></tr></table>"
)


@pytest.mark.parametrize(
    "text",
    [
        PAGE,
        "<!DOCTYPE html>\n<p>Short</p>",
        "  <html>\nhello",
        "<DIV>One</DIV><Div>two</Div><div class='x'>three</div>",
        "Hi<br>there<br/>and<br />again",
    ],
)
def test_a_page_is_html(text):
    assert looks_like_html(text)


@pytest.mark.parametrize(
    "text",
    [
        "Plain words, nothing else.",
        "Read it here <http://example.org/a?b=1> and <https://example.org/>",
        "Write to <ana.novak@example.org> or <span.smith@example.org>",
        "A pre tag <pre> and a track <track> are not structure",
        "Quoting one line break: use <br> for that.",
        "Closing tags only </div></td></tr>",
    ],
)
def test_a_message_is_not_html(text):
    assert not looks_like_html(text)


def test_the_threshold_is_adjustable():
    text = "<p>one</p><p>two</p>"
    assert not looks_like_html(text)
    assert looks_like_html(text, min_tags=2)
