"""FastAPI application for the SFCollab research reply agent."""

from __future__ import annotations

import asyncpg

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.generation import GenerationError, generate_draft_reply
from backend.feedback import get_feedback_summary, init_feedback_table, submit_feedback
from backend.retrieval_pinecone import retrieve


class AskRequest(BaseModel):
    """Request body for the /api/ask endpoint."""

    question: str = Field(..., min_length=1)


class RetrievedSnippet(BaseModel):
    """A retrieved knowledge base snippet returned to clients."""

    id: str
    title: str
    content: str
    score: float


class AskResponse(BaseModel):
    """Response payload for the /api/ask endpoint."""

    question: str
    retrieved_snippets: list[RetrievedSnippet]
    source_ids: list[str]
    draft: str
    grounded: bool


class FeedbackRequest(BaseModel):
    """Request body for feedback on a generated draft."""

    question: str = Field(..., min_length=1)
    draft: str = Field(..., min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    rating: str = Field(..., pattern="^(up|down)$")


app = FastAPI(title="sfcollab-research-reply-agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    """Initialize the feedback table on app startup."""
    try:
        await init_feedback_table()
    except Exception as exc:
        print(f"WARNING: Failed to initialize feedback storage on startup: {exc}")


@app.get("/")
def root() -> dict[str, str]:
    """Friendly root route for direct visits."""
    return {
        "message": "SFCollab Research Reply Agent API is running. See /api/health for status, or use the frontend to interact with this service."
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    """Basic health check."""
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    """Retrieve support context and generate a grounded draft reply."""
    snippets = retrieve(payload.question)
    try:
        draft_result = generate_draft_reply(payload.question, snippets)
    except GenerationError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "Unable to generate a draft reply right now.", "message": str(exc)},
        ) from exc

    return AskResponse(
        question=payload.question,
        retrieved_snippets=[RetrievedSnippet(**snippet) for snippet in snippets],
        source_ids=[snippet["id"] for snippet in snippets],
        draft=draft_result["draft"],
        grounded=draft_result["grounded"],
    )


@app.post("/api/feedback")
async def feedback(payload: FeedbackRequest) -> dict[str, str]:
    """Record feedback on a draft reply."""
    try:
        await submit_feedback(
            question=payload.question,
            draft=payload.draft,
            source_ids=payload.source_ids,
            rating=payload.rating,
        )
    except (RuntimeError, ConnectionError, OSError, asyncpg.PostgresError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "Feedback database is unavailable.", "message": str(exc)},
        ) from exc
    return {"status": "recorded"}


@app.get("/api/feedback/summary")
async def feedback_summary() -> dict[str, object]:
    """Return aggregate feedback counts."""
    try:
        return await get_feedback_summary()
    except (RuntimeError, ConnectionError, OSError, asyncpg.PostgresError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "Feedback database is unavailable.", "message": str(exc)},
        ) from exc
