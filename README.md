# sfcollab-research-reply-agent

This repository contains a two-step support reply assistant for SFCollab.

## Architecture

- The backend retrieves relevant help-center content from a knowledge base using Pinecone's integrated-inference vector search.
- It then uses Groq to draft a reply from the retrieved evidence.
- The frontend shows a two-panel UI:
  - Retrieved Evidence
  - Draft Reply
- The app requires human approval before any reply is treated as sent.

## Repository Layout

- `backend/`: FastAPI service, retrieval logic, and reply generation
- `frontend/`: Vite + React UI and end-to-end tests

## Live Deployment

- **Frontend:** https://sfcollab-research-reply-agent-git-main-semantic-search.vercel.app
- **Backend:** https://sfcollab-research-reply-agent.onrender.com
- **Health check:** https://sfcollab-research-reply-agent.onrender.com/api/health

## Fresh Clone Setup

These steps assume a brand-new clone and no prior local environment.

### 1. Set up the backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
cd backend
pip install -r requirements.txt
```

Create a `backend/.env` file with your Groq API key from the repository root:

```powershell
cd backend
@"
GROQ_API_KEY=your_groq_api_key_here
"@ | Set-Content .env
```

Run the backend locally:

```powershell
cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8020
```

### 2. Set up the frontend

Open a new terminal at the repository root and run:

```powershell
cd frontend
npm install
```

Create `frontend/.env` so the UI knows where the backend is running:

```powershell
@"
VITE_API_URL=http://127.0.0.1:8020
"@ | Set-Content .env
```

Run the frontend locally:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

### 3. Run tests

Backend checks from the repository root:

```powershell
python -m backend.test_retrieval
python -m backend.test_api
python -m backend.test_generation
```

Frontend end-to-end checks:

```powershell
cd frontend
npm run e2e
```

## Design Decisions

### Why Pinecone instead of local embeddings or TF-IDF?

The project started with TF-IDF for the same reasons noted below - it's simple, cheap, and sufficient for 32 static snippets. When asked to move to a RAG approach with a local vector database, we first tried ChromaDB with a local fastembed embedding model (BAAI/bge-small-en-v1.5, ONNX-based to avoid a PyTorch dependency). Real memory testing on Render's free tier showed this approach used 488MB of the platform's 512MB limit on a single cold request with no concurrent traffic - too close to the ceiling to be safe under real usage, and cold starts took ~46 seconds due to the embedding model downloading at boot.

We switched to Pinecone with integrated inference instead. Pinecone generates and stores embeddings on its own infrastructure, so the backend never loads an embedding model locally. The same memory diagnostic run against Pinecone showed a ~9-19MB memory delta and ~2-3 second response times - both dramatically better than the local-embedding approach, while keeping retrieval quality equal or better (embedding-based search is more resilient to typos and paraphrasing than TF-IDF was).

The refusal threshold (min_score) was empirically tuned by testing real on-topic, borderline, and off-topic queries against the deployed model rather than picked arbitrarily - see scripts/test_pinecone_retrieval.py for the test set used to find the score gap between relevant and irrelevant matches.

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
