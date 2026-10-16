# OpenCareer Domain Language

## Principal

The authenticated identity for one OpenCareer user. Every user-owned read and write is scoped to
exactly one Principal.

## Job Catalog

The shared collection of public job sources, jobs, versions, crawl runs, and source evidence. It
contains no candidate-private data.

## Candidate Data

User-owned career information: resumes, confirmed facts, job tracking, applications, matches,
interviews, and generated career artifacts.

## Conversation

One durable interaction thread between a Principal and an Agent. A Conversation owns an ordered,
append-only message history and may be linked to one active interview.

## Context Manifest

The durable record of which messages, compaction summary, memories, skills, and business records
were selected for one model turn. It records provenance, not model secrets.

## Compaction

A versioned summary of an older Conversation span used to fit a model context window. Compaction
never deletes or rewrites canonical messages.

## Durable Memory

A user-controlled fact or preference recalled across turns or Conversations. It is distinct from a
Compaction, which summarizes one Conversation.

## Runtime State

Short-lived coordination information such as process ownership, WebSocket presence, caches, leases,
and distributed locks. Runtime State is reconstructible and is not a source of truth.

## Blob

Binary user or crawler content, including resume originals, generated documents, reports, and raw
source snapshots. Every Blob has an owner or shared catalog scope, integrity hash, media type, and
lifecycle.

## Exact Origin

A browser origin represented by an explicit scheme, host, and optional port. Wildcards, paths,
queries, fragments, and suffix matching are not Exact Origins.
