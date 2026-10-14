"""Whether a message body is HTML source rather than text.

A body marked plain can still be a page: some exports flatten an HTML part
into the text field and keep the flag false. Offsets into it land in markup
and a model learns tag names, so both preparers leave such a body out and
count it. See ``docs/adr/0033``.

Standard library only: this plugin is meant to be cheap to install.
"""

import re
from itertools import islice

#: Tags a page is built from. Plain mail mentions one now and then; a page
#: is made of them.
STRUCTURAL = (
    "html",
    "head",
    "body",
    "div",
    "table",
    "tr",
    "td",
    "p",
    "br",
    "span",
    "font",
    "style",
    "meta",
)

#: How many structural tags make a page. Measured on the emails corpus:
#: none of the hand-labelled messages has three, and the HTML ones reviewers
#: skipped have between 17 and 92.
DEFAULT_MIN_TAGS = 3

# The name must end where a tag's name ends, so <pre>, <tracking@…> and
# <span.smith@example.org> are not tags. <http://…> never is.
_NAMES = "|".join(STRUCTURAL)
_TAG = re.compile(rf"<(?:{_NAMES})(?=[\s/>])[^<>]*>", re.IGNORECASE)
_OPENING = re.compile(r"\A\s*<(?:!doctype\s+html|html)(?=[\s>])", re.IGNORECASE)


def looks_like_html(text: str, min_tags: int = DEFAULT_MIN_TAGS) -> bool:
    """True for a page: one that opens like one, or has ``min_tags`` structural tags."""
    if _OPENING.match(text):
        return True
    # Stops at the threshold rather than counting a whole page
    return len(list(islice(_TAG.finditer(text), min_tags))) >= min_tags
