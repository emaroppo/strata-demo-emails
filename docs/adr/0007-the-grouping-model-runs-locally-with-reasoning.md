# 7. The grouping model runs locally, with reasoning on

**Status:** accepted

## The decision

Grouping uses Gemma 4 26B-A4B (Q8_0) served by llama.cpp on a machine of
our own, through its OpenAI-compatible API, with the model's reasoning
left on.

## Why local

Every decision sends the whole message body, unmasked, to the model:
the context is what makes "Lopez" in the third paragraph decidable.
Sending that to a hosted API would send the mail somewhere new
([ADR 1](0001-the-corpus-is-fetched-and-what-it-yields-stays-local.md)).
llama.cpp turns the reply's JSON schema into a grammar, so constrained
choice ([ADR 6](0006-an-llm-decides-each-mention-and-code-drives-the-loop.md))
works locally too.

## Why reasoning on, at six times the cost

Without reasoning a decision takes about 1.5 s; with it, about 9. On 20
easy messages both made identical decisions. The case that settled it
was a person referred to first by initials and later by title and
surname: without reasoning the model kept them apart under both prompts
tried; with reasoning, and a prompt that says initials and nicknames are
names too, it linked them. That inference — initials to a known name —
is the kind of case the LLM is there for.

## Consequences

- Grouping a thousand messages is an overnight run (about 11 hours), not
  an hour. It is a one-off, and cached.
- A prompt change was tested on the message it was meant to fix before
  being run on others; a revision that only helps easy cases is not
  worth the run.
- The prompt states two things and no heuristics: the class of every
  mention is settled, and initials, nicknames and titles are ways to name
  one person. A rule like "the name after a greeting is the recipient"
  was considered and rejected
  ([ADR 8](0008-grouping-errors-are-caught-by-checking-outputs.md)).
