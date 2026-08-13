# 0012 — btd is an optional per-project tool

Status: Accepted
Date: 2026-08-13

## Context

Making the journal authoritative
([ADR 0009](0009-journal-becomes-authoritative.md)) raises the stakes on
adoption. While markdown was the source of truth, pointing btd at a
directory changed nothing about that directory. Once state lives in an
event store, adopting btd for a list means the list's state now lives
somewhere the list's own repo may not want.

Two cases make this concrete. Todo lists carried inside project repos
are meant to be plain files a collaborator can read and edit with no
tooling. And bootstrap
[R6](../0000-project-bootstrap/REQUIREMENTS.md) requires views to merge
lists discovered in the working directory — lists that were never btd's
and whose owners never agreed to adopt it.

## Decision

**btd is opt-in per project, with a bootstrap/export lifecycle.**
Bootstrap imports an existing markdown todo directory as genesis events;
a final export writes the markdown view plus a history file, after which
btd can be removed from the project entirely.

The lifecycle rests on an exit guarantee, stated as a requirement:

> The markdown projection must always be complete enough that deleting
> the tsdb loses only history, never state.

Lists that have not adopted btd are **read-only markdown** — merged into
views, never journaled. This is how bootstrap R6's foreign-source
question resolves.

## Options

### Option 1 — Opt-in per project, bootstrap in and export out (chosen)
- [pro] Adoption is reversible, so trying btd on a repo carries no lock-in
- [pro] The "plain files in a repo" use case keeps working — collaborators need no tooling
- [pro] Foreign lists get a defined, honest status instead of being half-managed
- [con] Two classes of source to support in views: journaled and read-only
- [con] The exit guarantee constrains the projection permanently — it can never carry less than full state

### Option 2 — Every discovered source adopts btd
- [pro] One code path; every list is journaled and every view is uniform
- [con] Lock-in: dropping a todo directory into a working directory would silently claim it
- [con] Breaks the plain-files-in-a-repo case that made project-carried lists useful

### Option 3 — Journal foreign sources without adopting them
- [pro] Complete time series across everything the user sees
- [con] Their edit history is not ours to record — we would be inferring events from diffs of files someone else owns
- [con] Requires exactly the diff-to-event machinery ADR 0009 declined to build

## Rationale

The exit guarantee is what makes opt-in safe rather than merely polite.
A tool that can be removed without losing anything but history is a tool
worth trying on a real project; one that captures state is a commitment,
and commitments do not get made casually for a personal todo list. That
guarantee also caps how far the projection can drift from the journal —
it may lose history, never state, which keeps the markdown a complete
view rather than a summary.

Read-only foreign sources are the honest position. btd can show a list
it does not own; it cannot claim to know that list's history. Option 3
would manufacture events from diffs — inventing a record of changes it
did not observe, which is the same unsoundness ADR 0009 flipped
authority to escape.

## Consequences

- Views merge two classes of source. A read-only source cannot be
  mutated through btd, and the CLI has to say so rather than fail
  obscurely.
- `bootstrap` and `export` become part of the CLI surface, and export
  output is what the exit guarantee is tested against
  ([R1](REQUIREMENTS.md)).
- The markdown importer survives for bootstrap even though ADR 0009
  removes it from the read path.
- A project that exports and removes btd keeps its history only in the
  exported history file; re-adopting later means bootstrapping fresh.
