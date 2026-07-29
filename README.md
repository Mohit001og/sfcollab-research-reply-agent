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

## Notes

- The assistant refuses to guess when retrieval finds no relevant evidence.
- The UI keeps evidence and draft output separate so the review step stays explicit.
