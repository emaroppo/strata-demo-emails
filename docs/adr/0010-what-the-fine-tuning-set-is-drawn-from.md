# 10. What the fine-tuning set is drawn from

**Status:** accepted

## The decision

The thousand messages for fine-tuning are drawn from those the veto kept
([ADR 2](0002-gliner-masks-and-the-tagger-vetoes.md)), and:

- between 150 and 3,000 characters long;
- at least 40% with a link;
- every hand-labelled message that fits, the rest at random;
- without the few model-labelled messages that would need more than 20
  grouping decisions.

1,250 are drawn so the grouping checks can drop some and still leave a
thousand; if they leave fewer, disagreements are settled by hand until
the number is reached. (`anonymise.py --keep-from --min-chars
--max-chars --sample --url-share`, `group.py --max-decisions`.)

## Why

The kept messages are mostly short: the median is under 200 characters
and a quarter are under 85 — "can you call me", a bare link. They carry
nothing to template. The long tail is newsletters and memos, expensive to
group and to train on. Links appear in 27% of eligible messages; a
generator of realistic mail should handle them routinely, not rarely.
Hand-labelled messages have the cleanest spans there are, so all of them
go in, including the long ones. The decision cap drops 9 messages and
saves 6% of an overnight run.

## Consequences

- The sample is 45% messages with links (1,377 URL spans in 571
  messages); every other class appears in hundreds.
- Drawing from the veto's earlier output and re-running only the sample
  reproduces the same keep decisions in minutes, with spans recorded.
