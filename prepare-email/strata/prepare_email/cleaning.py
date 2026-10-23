"""What a body is cleaned of before it is stored, when a spec asks for it.

Ported from phishnet's cleaning, so that the corpora it prepared can be
prepared again from their source files and come out the same: the
quoted-printable soft breaks and escapes a sender's client left in the
text, ``[IMAGE]`` placeholders, and the ``>``, tab and space prefixes of
quoted lines. Then the edges are trimmed.

phishnet also removed disclaimers and footers. Here those are left in
the text, to be marked as spans rather than removed, because a mark is a
label and a stage writes none.
"""

import re

#: Removed wherever they appear. phishnet listed the soft break as the
#: raw string ``r"=\n"``, which never matches a line break; the corpora it
#: produced were cleaned of real ones, so that is what this removes.
DEBRIS = ("=\n", "=20", "=09", "=3D", "[IMAGE]")

#: Quoting and indentation at the start of a line. Cannot cross a line.
QUOTE_PREFIX = re.compile(r"^[\t >]+", re.MULTILINE)


def without_debris(text: str) -> str:
    """The body with client debris and quoting removed, edges trimmed."""
    # Line endings first: a soft break is "=" then the end of a line,
    # however the file ended its lines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for sequence in DEBRIS:
        text = text.replace(sequence, "")
    return QUOTE_PREFIX.sub("", text).strip()
