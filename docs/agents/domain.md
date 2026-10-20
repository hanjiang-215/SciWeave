# Domain Documentation

This repository has two isolated domain contexts: Research Mapping and LLM-Wiki. Shared terminology remains in the root `GLOSSARY.md`; each context owns its own governance records, storage boundary, validation and audit chain.

## Before exploring or changing domain behavior

- Read the root `GLOSSARY.md` and use its canonical terms.
- Read relevant architecture decisions in `docs/adr/`, if present.
- Read the relevant fer tickets in `.tickets/`; they are the authoritative source for requirements, decisions, acceptance criteria, and blockers.

Keep `GLOSSARY.md` focused on domain vocabulary, not implementation details. Record durable trade-off decisions as architecture decision records when appropriate; do not use the glossary as a specification or scratchpad.
