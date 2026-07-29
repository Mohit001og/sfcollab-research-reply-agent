"""Grounded reply generation for SFCollab support questions."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from groq import Groq
    from groq import APIError, AuthenticationError, RateLimitError
except ImportError as exc:  # pragma: no cover - dependency issue is surfaced clearly.
    Groq = None  # type: ignore[assignment]
    APIError = Exception  # type: ignore[assignment]
    AuthenticationError = Exception  # type: ignore[assignment]
    RateLimitError = Exception  # type: ignore[assignment]
    _GROQ_IMPORT_ERROR = exc
else:
    _GROQ_IMPORT_ERROR = None

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")


class GenerationError(RuntimeError):
    """Raised when grounded reply generation fails."""


_MODEL_NAME = "llama-3.3-70b-versatile"
_REFUSAL_TEXT = (
    "I don't have enough information in the help content to answer this confidently. "
    "Could you try rephrasing, or this may need a human to look into it."
)
_GROUNDING_STOP_WORDS = {
    "about",
    "after",
    "also",
    "answer",
    "are",
    "because",
    "been",
    "before",
    "being",
    "can",
    "could",
    "does",
    "each",
    "even",
    "from",
    "have",
    "help",
    "here",
    "into",
    "just",
    "like",
    "more",
    "most",
    "need",
    "only",
    "please",
    "should",
    "that",
    "their",
    "there",
    "this",
    "those",
    "through",
    "today",
    "very",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
    "would",
    "your",
    "you",
}


def _format_context(retrieved_snippets: list[dict[str, Any]]) -> str:
    """Format retrieved snippets into a compact prompt context."""
    blocks: list[str] = []
    for snippet in retrieved_snippets:
        blocks.append(
            f"Title: {snippet['title']}\nContent: {snippet['content']}"
        )
    return "\n\n".join(blocks)


def _tokenize(text: str) -> set[str]:
    """Extract lightweight content words for grounding checks."""
    tokens = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text.lower()):
        if token in _GROUNDING_STOP_WORDS:
            continue
        tokens.add(token)
    return tokens


def _build_snippet_token_set(retrieved_snippets: list[dict[str, Any]]) -> set[str]:
    """Collect normalized tokens from the retrieved evidence."""
    snippet_tokens: set[str] = set()
    for snippet in retrieved_snippets:
        snippet_tokens.update(_tokenize(snippet["title"]))
        snippet_tokens.update(_tokenize(snippet["content"]))
    return snippet_tokens


def _is_grounded_draft(draft: str, retrieved_snippets: list[dict[str, Any]]) -> bool:
    """Heuristically check whether the draft stays within retrieved evidence."""
    if not draft.strip():
        return False

    if "I don't have enough information" in draft:
        return True

    if "could you try rephrasing" in draft.lower() or "may need a human to look into it" in draft.lower():
        return True

    draft_tokens = _tokenize(draft)
    snippet_tokens = _build_snippet_token_set(retrieved_snippets)
    if not draft_tokens or not snippet_tokens:
        return False

    overlap = draft_tokens & snippet_tokens
    overlap_ratio = len(overlap) / len(draft_tokens)

    return len(overlap) >= 4 or overlap_ratio >= 0.28


def _build_local_draft(question: str, retrieved_snippets: list[dict[str, Any]]) -> str:
    """Build a deterministic grounded draft when Groq is unavailable."""
    if not retrieved_snippets:
        return _REFUSAL_TEXT

    lead_snippet = retrieved_snippets[0]
    supporting_titles = [snippet["title"] for snippet in retrieved_snippets[:3]]
    title_list = "; ".join(supporting_titles)
    content = lead_snippet["content"].rstrip(".")

    return (
        f"Based on the help content for '{question}', the relevant guidance is: {content}. "
        f"Relevant sources reviewed: {title_list}. "
        "If you want, I can help interpret this further before anything is sent."
    )


def generate_draft_reply(question: str, retrieved_snippets: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a grounded support reply from retrieved help snippets.

    Args:
        question: The user's original question.
        retrieved_snippets: Snippets returned by retrieval for this question.

    Returns:
        A dictionary with `draft` containing the reply text and `grounded`
        indicating whether the model was called on retrieved context.

    Raises:
        GenerationError: If the Groq request fails or the SDK is unavailable.
    """
    if not retrieved_snippets:
        return {"draft": _REFUSAL_TEXT, "grounded": False}

    if _GROQ_IMPORT_ERROR is not None or Groq is None:
        raise GenerationError(f"Groq SDK is unavailable: {_GROQ_IMPORT_ERROR}")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise GenerationError("GROQ_API_KEY is not set in the environment.")

    offline_test_mode = os.getenv("OFFLINE_TEST_MODE", "").lower() in {"1", "true", "yes"}

    context = _format_context(retrieved_snippets)
    prompt = (
        "You are a warm, helpful SFCollab support agent.\n"
        "Answer ONLY using the provided snippets below. If the snippets do not fully answer the question, "
        "say so honestly rather than filling gaps with outside knowledge. Do not invent features, policies, "
        "or steps not present in the snippets.\n"
        "Write directly to the user in plain text. Do not output JSON.\n\n"
        f"Question: {question}\n\n"
        f"Provided snippets:\n{context}\n"
    )

    client = Groq(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=_MODEL_NAME,
            messages=[
                {"role": "system", "content": "You write grounded support replies."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        draft = response.choices[0].message.content or ""
        if draft.strip():
            normalized_draft = draft.strip()
            if _is_grounded_draft(normalized_draft, retrieved_snippets):
                return {"draft": normalized_draft, "grounded": True}
            return {"draft": _REFUSAL_TEXT, "grounded": False}
    except (AuthenticationError, RateLimitError, APIError, Exception) as exc:
        if offline_test_mode:
            return {"draft": _build_local_draft(question, retrieved_snippets), "grounded": True}
        raise GenerationError(f"Failed to generate draft reply via Groq: {exc}") from exc

    if offline_test_mode:
        return {"draft": _build_local_draft(question, retrieved_snippets), "grounded": True}

    raise GenerationError("Failed to generate draft reply via Groq: empty response.")
