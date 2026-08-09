"""Pinecone-backed retrieval for the SFCollab help knowledge base.

This retriever uses Pinecone integrated inference, so embeddings are generated
on Pinecone's infrastructure during upsert and search. That means we do not
load any local embedding model here, keeping the server memory footprint near
zero compared to the Chroma + fastembed approach.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pinecone import Pinecone

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "sfcollab-knowledge-base")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "__default__")


@lru_cache(maxsize=1)
def load_knowledge_base() -> list[dict[str, Any]]:
    """Load and cache the knowledge base from disk."""
    with KNOWLEDGE_BASE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _document_text(entry: dict[str, Any]) -> str:
    """Build the retrieval text for a knowledge base entry."""
    return f"{entry['title']} {entry['content']}"


def _pinecone_client() -> Pinecone:
    """Create a Pinecone client from environment configuration."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY is not set")
    return Pinecone(api_key=api_key)


def _get_index():
    """Return the Pinecone index handle."""
    pc = _pinecone_client()
    return pc.Index(PINECONE_INDEX_NAME)


@lru_cache(maxsize=1)
def _prime_index() -> None:
    """Warm the index by reading the knowledge base once.

    The actual upsert happens in scripts/setup_pinecone_index.py. This module
    intentionally stays read-only at import time.
    """
    load_knowledge_base()


# This threshold was tuned from observed score separation in testing, not set
# arbitrarily; revisit it as we collect more real production queries over time.
def retrieve(query: str, top_k: int = 3, min_score: float = 0.79) -> list[dict[str, Any]]:
    """Return the most relevant help snippets for a query.

    Matches the return shape of backend.retrieval.retrieve and
    backend.retrieval_chroma.retrieve: a list of dictionaries with id, title,
    content, and score keys.
    """
    query = query.strip()
    if not query:
        return []

    _prime_index()
    index = _get_index()
    result = index.search(
        namespace=PINECONE_NAMESPACE,
        query={
            "inputs": {"text": query},
            "top_k": top_k,
        },
        fields=["title", "content"],
    )

    hits = result.result.hits
    matches: list[dict[str, Any]] = []
    for hit in hits:
        score = float(hit.score)
        if score <= min_score:
            continue

        matches.append(
            {
                "id": hit.id,
                "title": hit.fields.get("title", ""),
                "content": hit.fields.get("content", ""),
                "score": round(score, 3),
            }
        )

    return matches
