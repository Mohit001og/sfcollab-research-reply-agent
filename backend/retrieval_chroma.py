"""Chroma-based retrieval for the SFCollab help knowledge base."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from fastembed import TextEmbedding

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION_NAME = "sfcollab_knowledge_base"


@lru_cache(maxsize=1)
def load_knowledge_base() -> list[dict[str, Any]]:
    """Load and cache the knowledge base from disk."""
    with KNOWLEDGE_BASE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_embedder() -> TextEmbedding:
    """Create the fastembed model once per process."""
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def _document_text(entry: dict[str, Any]) -> str:
    """Build the retrieval text for a knowledge base entry."""
    return f"{entry['title']} {entry['content']}"


@lru_cache(maxsize=1)
def _build_collection() -> Collection:
    """Populate an in-memory Chroma collection with precomputed embeddings."""
    knowledge_base = load_knowledge_base()
    embedder = load_embedder()
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    documents = [_document_text(item) for item in knowledge_base]
    embeddings = list(embedder.embed(documents))

    collection.add(
        ids=[item["id"] for item in knowledge_base],
        documents=documents,
        embeddings=[embedding.tolist() for embedding in embeddings],
        metadatas=[dict(item) for item in knowledge_base],
    )
    return collection


def retrieve(query: str, top_k: int = 3, min_score: float = 0.1) -> list[dict[str, Any]]:
    """Return the most relevant help snippets for a query.

    This mirrors backend.retrieval.retrieve so it can be swapped in later.
    """
    query = query.strip()
    if not query:
        return []

    embedder = load_embedder()
    collection = _build_collection()
    query_embedding = list(embedder.embed([query]))[0].tolist()

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["metadatas", "distances"],
    )

    matches: list[dict[str, Any]] = []
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    for metadata, distance in zip(metadatas, distances):
        score = max(0.0, 1.0 - float(distance))
        if score <= min_score:
            continue
        matches.append(
            {
                "id": metadata["id"],
                "title": metadata["title"],
                "content": metadata["content"],
                "score": round(score, 3),
            }
        )
    return matches
