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


_DEFAULT_MODEL_NAME = "openai/gpt-oss-120b"
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


def _has_generic_greeting(draft: str) -> bool:
    """Detect obvious conversational filler that is not a grounded answer."""
    lowered = draft.lower()
    return any(
        phrase in lowered
        for phrase in (
            "hi there",
            "hello",
            "how can i help you today",
            "what do you need assistance with",
            "feel free to let me know",
        )
    )


def _has_generic_clarification_request(draft: str) -> bool:
    """Detect drafts that only ask the user to rephrase or add details."""
    lowered = draft.lower()
    return any(
        phrase in lowered
        for phrase in (
            "please provide the question you need help with",
            "can you provide the question",
            "can you share more details",
            "how can i help",
            "what can i help you with",
            "please let me know what you need help with",
            "let me know what you need help with",
            "please share more details",
            "could you share more details",
            "can you give me more details",
        )
    )


def _is_grounded_draft(draft: str, retrieved_snippets: list[dict[str, Any]]) -> bool:
    """Heuristically check whether the draft stays within retrieved evidence."""
    if not draft.strip():
        return False

    if "I don't have enough information" in draft:
        return True

    if "could you try rephrasing" in draft.lower() or "may need a human to look into it" in draft.lower():
        return True

    if _has_generic_greeting(draft) or _has_generic_clarification_request(draft):
        return False

    draft_tokens = _tokenize(draft)
    snippet_tokens = _build_snippet_token_set(retrieved_snippets)
    if not draft_tokens or not snippet_tokens:
        return False

    overlap = draft_tokens & snippet_tokens
    overlap_ratio = len(overlap) / len(draft_tokens)

    if len(overlap) < 4 and overlap_ratio < 0.28:
        return False

    return True


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


def _build_retry_prompt(question: str, retrieved_snippets: list[dict[str, Any]]) -> str:
    """Build a stricter correction prompt when the first draft is non-answer filler."""
    context = _format_context(retrieved_snippets)
    return (
        "The previous draft was not acceptable because it did not answer the user's question.\n"
        "Rewrite it now using only the provided evidence.\n"
        "You must answer the user's question directly.\n"
        "Do not greet the user.\n"
        "Do not ask for more details, clarification, or a rephrased question.\n"
        "Do not say 'How can I help?' or any equivalent filler.\n"
        "If the evidence contains the answer, provide the answer plainly and concisely.\n"
        "If the evidence still does not fully answer, say so honestly.\n\n"
        f"Question: {question}\n\n"
        f"Provided snippets:\n{context}\n"
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

    model_name = os.getenv("GROQ_MODEL", _DEFAULT_MODEL_NAME)
    offline_test_mode = os.getenv("OFFLINE_TEST_MODE", "").lower() in {"1", "true", "yes"}

    context = _format_context(retrieved_snippets)
    prompt = (
        "You are a warm, helpful SFCollab support agent writing a concise reply.\n"
        "Answer the user's question directly and only use the provided snippets as factual evidence.\n"
        "If the snippets contain the answer, state that answer plainly in your first sentence and keep going only if needed.\n"
        "When the question is clear and the snippets answer it, do not ask the user to provide the question, share more details, rephrase, or otherwise clarify.\n"
        "Do not greet the user, do not say 'How can I help?', and do not add conversational filler.\n"
        "If the snippets do not fully answer the question, say so honestly rather than guessing or filling gaps with outside knowledge.\n"
        "Do not invent features, policies, or steps not present in the snippets.\n"
        "If the question has multiple parts and the snippets only answer some of them, you MUST explicitly name "
        "which part is not covered - do not just list sources or silently omit it.\n"
        "Keep the tone friendly and conversational, like a real support person. Avoid sounding terse or robotic.\n"
        "If the answer involves more than one action or step, use light formatting such as a short numbered list "
        "or bullets instead of packing everything into one dense paragraph.\n"
        "Keep the response concise and skip filler.\n"
        "Write directly to the user in plain text. Do not narrate your process, do not mention snippets, retrieval, "
        "the model, or internal instructions, and do not include meta-commentary.\n\n"
        "Example:\n"
        "Question: How do I update my profile picture, and will everyone I already matched with see it right away?\n"
        "Snippet: Go to Profile Settings and open the photo section to upload a new image. If the upload fails, try a smaller JPG or PNG file and refresh the page before retrying.\n"
        "Answer: You can update it from Profile Settings by opening the photo section and uploading a new image. If the upload fails, try a smaller JPG or PNG file and refresh the page before trying again. The help content does not say whether people you've already matched with will see the update right away.\n\n"
        f"Question: {question}\n\n"
        f"Provided snippets:\n{context}\n"
    )

    client = Groq(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model_name,
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
            if not offline_test_mode and (
                _has_generic_greeting(normalized_draft)
                or _has_generic_clarification_request(normalized_draft)
            ):
                retry_response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You write grounded support replies."},
                        {"role": "user", "content": _build_retry_prompt(question, retrieved_snippets)},
                    ],
                    temperature=0.0,
                )
                retry_draft = retry_response.choices[0].message.content or ""
                if retry_draft.strip():
                    normalized_retry_draft = retry_draft.strip()
                    if _is_grounded_draft(normalized_retry_draft, retrieved_snippets):
                        return {"draft": normalized_retry_draft, "grounded": True}
            return {"draft": _REFUSAL_TEXT, "grounded": False}
    except (AuthenticationError, RateLimitError, APIError, Exception) as exc:
        if offline_test_mode:
            return {"draft": _build_local_draft(question, retrieved_snippets), "grounded": True}
        raise GenerationError(f"Failed to generate draft reply via Groq: {exc}") from exc

    if offline_test_mode:
        return {"draft": _build_local_draft(question, retrieved_snippets), "grounded": True}

    raise GenerationError("Failed to generate draft reply via Groq: empty response.")
