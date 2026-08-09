"""FastAPI application for the SFCollab research reply agent."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.generation import GenerationError, generate_draft_reply
from backend.retrieval import retrieve


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


app = FastAPI(title="sfcollab-research-reply-agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/debug/pinecone-memory-test")
def pinecone_memory_test() -> dict[str, object]:
    # TEMPORARY - DIAGNOSTIC ONLY - REMOVE BEFORE MERGE
    import resource
    from time import perf_counter

    from backend.retrieval_pinecone import PINECONE_INDEX_NAME, PINECONE_NAMESPACE
    from backend.retrieval_pinecone import retrieve

    print(
        f"DEBUG PINECONE SETTINGS: index={PINECONE_INDEX_NAME!r} namespace={PINECONE_NAMESPACE!r}"
    )
    memory_before_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    started = perf_counter()
    sample_query_result = retrieve("How do I update my profile picture?")
    elapsed_seconds = perf_counter() - started
    memory_after_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return {
        "memory_before_mb": memory_before_mb,
        "memory_after_mb": memory_after_mb,
        "memory_delta_mb": memory_after_mb - memory_before_mb,
        "sample_query_result": sample_query_result,
        "elapsed_seconds": elapsed_seconds,
        "debug_index_name": PINECONE_INDEX_NAME,
        "debug_namespace": PINECONE_NAMESPACE,
    }
