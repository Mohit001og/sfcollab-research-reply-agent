# sfcollab-research-reply-agent

This project is a two-step grounded research + draft-reply agent for SFCollab, a startup co-founder matchmaking platform.

The first step retrieves the most relevant help-center snippets from a local knowledge base using TF-IDF. The next phase will use those grounded snippets to draft a reply, but this repository intentionally stops short of sending anything automatically.

## Local Setup

This repo currently contains the knowledge base and retrieval layer only.

1. Set up the backend environment and install dependencies from `backend/requirements.txt`.
2. Configure `backend/.env` from `backend/.env.example` when you are ready to add API keys.
3. Install frontend dependencies in `frontend/` after scaffolding.

## Approval Note

This project deliberately does not auto-send anything. Human approval is required at every step before any reply is sent or any action is taken on behalf of a user.
