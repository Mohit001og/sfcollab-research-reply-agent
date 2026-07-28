"""FastAPI application for the SFCollab research reply agent."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from generation import GenerationError, generate_draft_reply
from retrieval import retrieve


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
    draft: str
    grounded: bool


app = FastAPI(title="sfcollab-research-reply-agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        draft=draft_result["draft"],
        grounded=draft_result["grounded"],
    )
