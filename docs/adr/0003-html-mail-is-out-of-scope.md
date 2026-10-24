# 3. HTML mail is out of scope

**Status:** accepted; removal when prepared amended by record 0013 (proposed)

## The decision

Messages whose body is HTML are excluded: they are detected when
prepared and removed from the catalog, and the labelling guide treats a
skip as "out of scope" rather than "too hard".

## Why

Character offsets in markup are offsets into tags, attributes and
entities as much as into text, and Label Studio renders the page rather
than the characters, so a reviewer marks spans on what they see while
the model reads something else. Converting HTML to text first is a
preparer's job with its own choices to make (links, tables, hidden
text), and the plain-text messages are plenty for the goal.

## Consequences

- 146 HTML messages were removed from the catalog, a backup of the
  catalog taken first.
- Newsletters, which are often HTML, are under-represented. For a
  template generator that is acceptable; the selection
  ([ADR 10](0010-what-the-fine-tuning-set-is-drawn-from.md)) drops most
  newsletter-length messages anyway.

## Amendments

- **HTML mail is kept when prepared, and skipped for review instead**
  ([record 0013](0013-html-mail-is-kept-and-skipped-for-review.md)). The
  preparation stages serve more than one project, so they keep a body
  with HTML in it and record its tag count; each project skips such
  samples in the label sets it reviews, with source `import`, and leaves
  them out of a dataset version by selection. Not labelling markup still
  stands.
