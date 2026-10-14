# 12. Grouping is this project's own package, not a strata plugin

**Status:** accepted

## The decision

The grouper lives in this repository as `group-entities/`, a plain
package (`group_entities`), beside `prepare-email/`. It is not in the
`strata` namespace and registers no entry points.

## Why

`prepare-email` is a strata plugin: strata discovers it, and it is
written the way a third party would write one. The grouper is neither: it
is the next stage of this pipeline, and nothing in strata calls it. A
`strata.` name would promise an integration that isn't there.

## When it would move

If a second project needs "an LLM assigns structure to candidate spans,
validated in code", it becomes a `strata.models` plugin. Before that,
groupings would need a home in strata's contracts — a span with an entity
id, which `Span` cannot carry today — so they can be stored as
annotations, reviewed, and compared with a person's.
