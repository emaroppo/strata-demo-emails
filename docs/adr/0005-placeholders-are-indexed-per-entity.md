# 5. Placeholders are indexed per entity, one class at a time

**Status:** accepted

## The decision

Masked text carries one placeholder per entity, numbered by first
appearance within its class: "[PER_1] met [PER_2] at [ORG_1]. [PER_2]
thanked [PER_1]." Mentions are grouped one class at a time, so a person
and an organisation can never share a number. Each manifest line records
every span with the entity it went into.

## Why

A generator trained on "[PER] met [PER]" cannot learn who did what to
whom; the template it produces has no structure for replacement to keep.
With indexed placeholders, filling them in is a mapping from entity to
value, consistent by construction: "Maria Lopez", "Lopez" and "Senator
Lopez" all become the same fake name.

Grouping within a class keeps each decision small and makes a whole kind
of error impossible. What it gives up is links across classes — an email
address that belongs to a person, an acronym tagged as an organisation
when it names a person. Those are a later, separate step.

## Consequences

- The spans with their entities are what replacement needs; the masked
  text alone loses which span became which placeholder.
- A detection error in class becomes a grouping limit: a person's
  initials tagged ORG cannot join that person's other mentions. Finding
  strings tagged with more than one class is the check for it.
- An entity grouped with its abbreviation reads oddly once masked
  ("[ORG_2], aka [ORG_2]"); a hint on the placeholder may be needed when
  replacement is built.
