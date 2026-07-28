"""Grounded reply generation for SFCollab support questions."""

from __future__ import annotations

import os
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


def _format_context(retrieved_snippets: list[dict[str, Any]]) -> str:
    """Format retrieved snippets into a compact prompt context."""
    blocks: list[str] = []
    for snippet in retrieved_snippets:
        blocks.append(
            f"Title: {snippet['title']}\nContent: {snippet['content']}"
        )
    return "\n\n".join(blocks)


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
    except (AuthenticationError, RateLimitError, APIError, Exception) as exc:
        raise GenerationError(f"Failed to generate draft reply via Groq: {exc}") from exc

    return {"draft": draft.strip(), "grounded": True}
