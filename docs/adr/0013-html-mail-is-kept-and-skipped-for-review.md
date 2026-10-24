# 13. HTML mail is kept, measured, and skipped for review by a project

**Status:** proposed; amends record 0003

## The decision

A message whose plain body is HTML source is kept in the catalog when the
preparation stages run (`parse-rfc822`, `parse-message-json`). The email
type records how many structural tags its text has, as the `html_tags`
fact. Leaving HTML out is then a choice each project makes, in two places:

- **For review**, `skip-html` writes a skip, with source `import`, for
  every sample in the collections named that looks like a page, by the
  same rule the preparers used (opens like one, or has three structural
  tags). It writes an answers file, which `strata-catalog import-answers`
  lands as one run. A skipped sample is out of the label set's review
  queue and out of its dataset versions alike.
- **For a dataset version**, a selection condition on `html_tags`, once
  strata's selection spec exists (its record 0050). Its threshold should
  be the same three tags.

A message with no plain part at all is still dropped, as `no_plain_part`.

## What this amends, and why

Record 0003 removed HTML mail when it was prepared. That made the
preparation decide what every project trains on and reviews, and it left
nothing behind to change one's mind with: 146 messages were deleted from
the catalog. Preparation stages now run inside the catalog over raw files
it keeps (strata's record 0046), and their output is meant to serve more
than one project, so they keep what they can store and record what they
measured. What 0003 got right still stands: offsets into markup are not
what a reviewer sees, so HTML is not labelled. A skip says so in the
catalog, where it keeps the sample out of review without removing it.

The skip comes from a rule, so it carries source `import`, never
`human`. It is written in the catalog rather than in Label Studio,
because a skip made there comes back as a person's answer, and because a
sample is only in Label Studio once a push has spent a place in a batch
on it.

## Consequences

- `skip-html` is in `prepare-email`, beside the rule, behind its
  `catalog` extra: the stages themselves still need no catalog.
- It writes the answers file as plain JSON in the layout `import-answers`
  reads, so it runs against a catalog too old to import one. The import
  needs a newer catalog than this project's environment pins.
- The two preparers (`eml`, `email-json`) still drop HTML, and this
  project's own catalog still lacks the 146 messages 0003 removed. They
  retire when this project prepares through specs.
- A skip is per label set, so a project skips HTML once in each label set
  it reviews, and again after new mail is prepared.
