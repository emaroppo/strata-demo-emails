# Labelling guidelines

**Version 1**, 2026-10-14. The gold set records the version it was
labelled under; a rule change is a new version, not an edit to this one.

Every name, organisation, place, address and handle below is invented. A
guide for anonymising mail quotes no one from the mail.

## What a label is for

Every span labelled here is something the anonymiser replaces with a
placeholder of its class. So the question to ask of a piece of text is not
"is this an entity?" but "should this be masked, and if it were, would the
result still say the right thing?" "Dear [PER], I met [PER] at [LOC]" is the
target: one placeholder per thing, no more and no fewer.

Classes: PER, ORG, LOC, DATE, EMAIL, PHONE, URL, ATTACHMENT.

## Boundaries

- **The span is the thing, not the field it sits in.** `Location: B2` labels
  `B2`; `Room: 4120` labels `4120`; `Phone: 202-555-0100` labels the number.
- **No surrounding whitespace or punctuation.** No leading spaces, no
  trailing comma after a name in a list (`Tom, Ana Novak` is `Tom` and
  `Ana Novak`). Brackets around a URL are the one allowance; see URL
  below.
- **Punctuation that belongs to the thing stays.** `U.S.`, `Inc.`, `Ave.`,
  `Hale-Moreno`, and brackets that are part of a name:
  `Coastal Research Office (CRO)` is one ORG, closing bracket included.
- **Each stretch of text once.** One region, one label. If a span is wrong,
  correct it; don't add a second one on top. Overlapping and duplicate
  regions are always a mistake.

## One placeholder per thing

Two errors matter most, and both are about where one entity ends and the next
begins (see `docs/anonymisation-approaches.md`):

- **Fragmenting** one entity into two spans. "Dear [PER] [PER]" reads as two
  people.
- **Merging** two entities into one span. One placeholder hides that there
  were two.

So:

- **Every title goes in the person's PER span.** `Sen. Maria Lopez` is one
  PER over the whole of it, giving "[PER]". This holds for every kind of
  title, with no judgement about which ones matter: courtesy titles (`Mr.`,
  `Dr.`), ranks (`Lieutenant General Paul R. Hart`), public office
  (`Governor Ellen Ward`, `Congressman Tim Osei`), and roles in a company or
  NGO (`Senior Vice President Dana Kim`).

  *Why always:* a high office names one person by itself ("Secretary of
  State [PER]" still says who it was), so those titles must be masked. A
  company or NGO role identifies someone only together with its
  organisation, which is masked as its own ORG, so masking the role costs
  nothing. Drawing a line between the two would mean deciding, case by
  case, whether a mayor, an ambassador or a state legislator counts, and a
  model trained on that line learns inconsistent span starts. Masking a
  title that didn't need it costs readability; leaving out one that did
  leaks who it was.

  *What counts as the title:* the whole run of title words directly before
  the name, modifiers included: `former Energy Secretary Ruth Adler`,
  `State Representative Joe Brandt`, `Senior Vice President Dana Kim`. An
  organisation or a place that is part of the title goes in with it,
  wherever it sits: `former EPA Administrator Ruth Adler`,
  `Northfield Tenants Union President Sam Okafor`,
  `Deputy Party Chairman Leo Grant`, `United States Senator Maria Lopez` and
  `Riverside Mayor Ellen Ward` are each one PER, not an ORG or LOC and a
  PER. Splitting the organisation or place out only works when it comes
  first, and a rule that depends on word order gives arbitrary differences
  between cases that mean the same thing.

  Never label the title as a span of its own: `Sec.` + `Maria Lopez` as two
  PER spans is a fragmented name. A title with no name after it ("the
  Senator said") is not labelled, unless it stands for a person (see
  couples below).
- **A title on the line after the name,** as in a signature block
  (`Maria Lopez` with `United States Senator` beneath it), may be labelled
  either of two ways, and both are right:
  - one PER over the name, the line break and the title, giving "[PER]";
  - PER over the name, and each place or organisation inside the title
    under its own class, leaving the rest of the title as it is:
    "[PER]\n[LOC] Senator", "[PER]\nDirector, [ORG]". A title with nothing
    inside it ("Campaign Manager") is then left as it is.
- **Couples sharing a surname are two people.** `Anna and Mark Reyes` is
  PER `Anna` and PER `Mark Reyes`, giving "[PER] and [PER]". `Anna and` is
  never a span. The same holds when the first person is only a title:
  `Mr. and Mrs. Luis Ortega` is PER `Mr.` and PER `Mrs. Luis Ortega`, since
  `Mr.` there stands for a person.
- **Names in a list are separate spans,** one per line or per comma, even
  when nothing but a newline separates them.

## By class

**PER**: people, by full name, part of a name, nickname or initials. Initials
used as a person's name are PER, consistently, wherever they appear: if `MK`
is a person in one line of a schedule, it is PER in every line. A surname
used to mean the campaign ("Lopez's deputy chairman", "5:30pm Lopez: fund
raiser") is still the person: PER.

**ORG**: companies, campaigns, parties, agencies, schools, publications,
mailing lists. `Daily Ledger` is ORG wherever it appears, including
"Daily Ledger columnist". A school is ORG even next to a graduation year:
`Graduate Hillcrest Law School 2011` is ORG `Hillcrest Law School` and DATE
`2011`. A domain used as an organisation's name (`CoastalResearch.org` in
running text) is ORG, not EMAIL or URL.

**LOC**: anywhere physical, at any grain: countries, states, cities,
addresses, venues, buildings, motorway exits, and rooms. A room is the
finest part of an address and narrows down where someone works, so it is
masked: `Room: 4120` labels `4120`; in running text, "meet in Room 4120"
labels `Room 4120`, and a named room (`Lakeview Room`) is LOC whole.
Numbers that only look like rooms are not places: conference-call room
codes, dial-in PINs and meeting IDs are left unlabelled. State abbreviations
are LOC (`IA`, `SC`, `NH`, `DC`). An address is one LOC from its first
word: `East Riverside OH 44000`, not ORG `East` and LOC `Riverside OH 44000`.

**DATE**: dates and times, alone or together: `Dec. 14`,
`Wednesday January 13`, `5:30pm`, `2011`. A date followed by a place is two
spans: `Wednesday January 13 – DC` is DATE `Wednesday January 13` and LOC
`DC`.

**EMAIL**: full addresses only, with the `@`, without `mailto:` or angle
brackets.

**URL**: the whole URL from scheme or `www.` to its last character, once.
A fragment of a URL is never labelled separately. Brackets around it
(`<http://…>`, `[ http://… ]`) may be included or left out, but if they are
included both go in: a span never ends on a `)` or `]` it didn't open, or
opens one it doesn't close.

Social media handles are URL too, `@` included: `@ana_novak`, `@CoastalRO`,
whether the handle is a person's or an organisation's. A handle followed
directly by its own profile link may share one span with it:
`@ana_novak [ http://twitter.com/ana_novak ]` is one URL.

**PHONE**: the number, from its first digit or `+` or `(` to its last digit.
Labels like `(office)` or `(cell)` stay outside.

**ATTACHMENT**: the file name of an attached file.

## Hashtags

A hashtag is not an entity of its own, but an entity inside one is
labelled, even though it is only part of a word: `#2016debate` labels DATE
`2016`, and the `#` and the rest of the tag stay outside. A tag that is
nothing but an entity (`#AnaNovak`) labels the name without the `#`.

## Skips

A skip means what it means everywhere in strata: the sample was reviewed
and nothing in the label set applies to it. It is neither training data
nor queue. Use it for a message the labelling doesn't apply to, such as
HTML source or text too garbled to read.

A message the labelling does apply to, but with nothing to flag, is not a
skip: submit it with no spans. That empty answer is training data, and
the model needs it to learn when to tag nothing.
