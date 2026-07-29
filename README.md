# sfcollab-research-reply-agent

This repository contains a two-step support reply assistant for SFCollab.

## Architecture

- The backend retrieves relevant help-center content from a local knowledge base using TF-IDF.
- It then uses Groq to draft a reply from the retrieved evidence.
- The frontend shows a two-panel UI:
  - Retrieved Evidence
  - Draft Reply
- The app requires human approval before any reply is treated as sent.

## Repository Layout

- `backend/`: FastAPI service, retrieval logic, and reply generation
- `frontend/`: Vite + React UI and end-to-end tests

## Design Decisions

### Why TF-IDF instead of embeddings or a vector database?

This project uses TF-IDF because the knowledge base is small and static at 32 snippets. TF-IDF is easy to inspect, cheap to run, and does not add an extra paid dependency or infrastructure layer just to retrieve a few dozen help articles. For this scale, it is a deliberate simplicity choice, not a limitation.

### Why Groq for generation?

Groq was chosen because it provides a free tier that did not require billing setup for this task. That made it the most practical option for a grounded draft-reply demo without adding extra account setup friction.

### What happens if generation fails?

The backend returns an honest `503` via `GenerationError`. It does not silently substitute a fake answer in production. That behavior was specifically tested during the audit so failures stay visible instead of being disguised.

`OFFLINE_TEST_MODE` exists only for local development and CI testing. It is never set in the production Render environment, so a real user always gets either a genuine Groq-generated answer or an honest 503 error - never a substituted fake draft.

### What does `grounded: true/false` mean?

- `grounded: true` means the draft was generated from retrieved evidence.
- `grounded: false` means retrieval found no relevant snippets, so the system refused instead of inventing an answer.

To verify it manually, compare the draft text against the visible snippets in the UI. Every factual claim in a grounded draft should trace back to one of those snippets.

Why isn't there a way to filter or select which knowledge base entries to search? Retrieval automatically searches the full knowledge base for every question. There's no manual filtering because the system finding relevant evidence on its own - the same way a real support search would - is the point of the retrieval step.

The full set of retrieved_snippets shown in the UI is the complete and only source material available to the draft - there is no hidden retrieval step, so any claim in the draft should be traceable to one of the visible snippets above it.

## Notes

- The assistant refuses to guess when retrieval finds no relevant evidence.
- The UI keeps evidence and draft output separate so the review step stays explicit.
