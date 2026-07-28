"""TF-IDF based retrieval for the SFCollab help knowledge base."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"


@lru_cache(maxsize=1)
def load_knowledge_base() -> list[dict[str, str]]:
    """Load and cache the knowledge base from disk.

    Returns:
        A list of knowledge base entries, each containing `id`, `title`, and
        `content` fields.
    """
    with KNOWLEDGE_BASE_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


_KNOWLEDGE_BASE = load_knowledge_base()
_DOCUMENTS = [f"{item['title']} {item['content']}" for item in _KNOWLEDGE_BASE]
_CUSTOM_STOP_WORDS = {
    "help",
    "today",
    "weather",
    "tax",
    "taxes",
    "what",
    "whats",
    "can",
    "could",
    "please",
    "like",
    "you",
    "me",
}
_VECTORIZER = TfidfVectorizer(stop_words=sorted(ENGLISH_STOP_WORDS.union(_CUSTOM_STOP_WORDS)))
_MATRIX = _VECTORIZER.fit_transform(_DOCUMENTS)


def retrieve(query: str, top_k: int = 3, min_score: float = 0.1) -> list[dict[str, Any]]:
    """Return the most relevant help snippets for a query.

    Args:
        query: The user question or search phrase.
        top_k: Maximum number of snippets to return.
        min_score: Minimum cosine similarity score required for inclusion.

    Returns:
        A list of matches ordered by score, each with `id`, `title`, `content`,
        and `score` keys. Scores are rounded to three decimals. If no result
        clears the threshold, an empty list is returned.
    """
    query_tokens = set(_VECTORIZER.build_analyzer()(query))
    query_vector = _VECTORIZER.transform([query])
    scores = cosine_similarity(query_vector, _MATRIX).ravel()
    ranked_indices = scores.argsort()[::-1]

    results: list[dict[str, Any]] = []
    for index in ranked_indices[:top_k]:
        score = float(scores[index])
        if score <= min_score:
            continue
        document_tokens = set(_VECTORIZER.build_analyzer()(_DOCUMENTS[index]))
        if len(query_tokens & document_tokens) < 2:
            continue
        item = _KNOWLEDGE_BASE[index]
        results.append(
            {
                "id": item["id"],
                "title": item["title"],
                "content": item["content"],
                "score": round(score, 3),
            }
        )
    return results
