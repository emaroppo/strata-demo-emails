# 8. Grouping errors are caught by checking outputs, not by prompt rules

**Status:** accepted

## The decision

When the model merged a recipient with a sender, the fix considered was a
line in the prompt: the name after a greeting is who the email is to, the
sign-off who it is from. It was rejected. Instead the output is checked:
for every message, the rule-only grouper runs beside the LLM, and a
message where the two group differently is left out of what is trained
on unless someone has judged the LLM right. (`rules_agree` in the
manifest.)

## Why not the rule

It is too simple to be true often enough: forwarded mail, "Thanks, Sam"
in the middle of a body, a list of names after "Hi". A heuristic in the
prompt would trade one error for others, invisibly, in every message.

## Why disagreement

The two fail in opposite directions. The LLM over-merges related things
(a person into their organisation, a sub-region into its region); the
rules miss variants and merge on shared words. A message where they agree
is one where neither failure happened. On 100 judged messages they
agreed on 42, and on all 42 both were right; all four LLM errors were in
messages where they disagreed.

## Consequences

- It costs the hard cases: in that sample the LLM was right on 20 of the
  24 disagreements. Judged disagreements are kept, so the cost is reading
  time rather than data ([ADR 11](0011-every-grouped-message-is-judged.md)).
- A merge both make passes. The first seen: a first name used as a
  salutation joined to a different person with that first name, which
  the rules do by containment and the model did too. A targeted check —
  an entity holding both a bare salutation name and someone's full name —
  is the next one to add.
