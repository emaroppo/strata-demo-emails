# 2. GLiNER masks, the tagger vetoes

**Status:** accepted

## The decision

A message is masked with the fine-tuned GLiNER model. The BIO tagger then
reads the same message, and if it flags any character GLiNER left in
clear, the message is dropped rather than kept. Messages labelled by hand
are masked with their own labels and always kept.
(`scripts/anonymise.py`)

## Why two models, and why drop

On the interim dev set the two fail differently. GLiNER finds entities
more exactly (strict F1 0.82 against 0.72) and almost never splits one
into fragments; the tagger leaves fewer entities unmasked (11% against
13%). Neither alone left most messages fully clean: about half of the
messages with entities had something in clear either way.

The union of their spans cleaned more messages (61%) but fragmented
names into several placeholders, which damages exactly the text the
output is for. Disagreement turned out to be the better signal: where the
tagger sees something GLiNER missed is where a leak is likeliest. On dev,
keeping only messages where they agreed kept 19 of 29, and none of those
had anything left in clear.

Dropping costs data, and the corpus can afford it: the goal is a thousand
clean messages, not every message.

## Consequences

- Over the whole corpus the filter keeps 29% of messages (3,676 of
  12,735), plus the 146 labelled by hand.
- It can only catch what one of the two models sees. A name neither
  detects — a surname in lower case, a misspelling — passes; that is what
  the hand audit ([ADR 4](0004-numbers-are-dev-numbers-until-a-gold-set-exists.md))
  and the judging ([ADR 11](0011-every-grouped-message-is-judged.md))
  are for.
- A name that slips through once tends to slip through everywhere it
  appears in the same form, so repeated strings are worth checking across
  the corpus rather than message by message.
