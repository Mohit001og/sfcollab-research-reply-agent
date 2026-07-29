"""End-to-end retrieval plus grounded generation verification."""

from __future__ import annotations

import os
from time import perf_counter

from backend.generation import GenerationError, generate_draft_reply
from backend.retrieval import retrieve


TEST_CASES = [
    "How do I update my profile picture?",
    "What's the weather like today?",
    "Can I use SFCollab if I'm not based in the US?",
    "How do I update my profile picture and will it show up immediately to people I've already matched with?",
]

COMPOUND_QUESTION = "How do I update my profile picture and will it show up immediately to people I've already matched with?"


def print_case(question: str) -> None:
    """Run retrieval then generation for a single test question."""
    print(f"QUESTION: {question}")
    retrieved = retrieve(question)
    if not retrieved:
        print("RETRIEVED: NO MATCH")
    else:
        print("RETRIEVED:")
        for snippet in retrieved:
            print(f"- {snippet['title']} ({snippet['score']:.3f})")

    start = perf_counter()
    try:
        result = generate_draft_reply(question, retrieved)
        elapsed = perf_counter() - start
        print(f"ELAPSED: {elapsed:.3f}s")
        print(f"GROUNDED: {result['grounded']}")
        print("DRAFT:")
        print(result["draft"])
    except GenerationError as exc:
        elapsed = perf_counter() - start
        print(f"ELAPSED: {elapsed:.3f}s")
        print(f"ERROR: {exc}")
    print()


def assert_compound_case_is_grounded() -> None:
    """Verify the validator allows a hedged partial answer through."""
    retrieved = retrieve(COMPOUND_QUESTION)
    result = generate_draft_reply(COMPOUND_QUESTION, retrieved)
    assert retrieved, "Expected retrieval to return evidence for the compound question."
    assert result["grounded"] is True, "Expected the partial-answer draft to remain grounded."
    assert "I don't have enough information" not in result["draft"], "Expected an answer, not a refusal."


def main() -> None:
    """Run all end-to-end generation checks."""
    os.environ.setdefault("OFFLINE_TEST_MODE", "true")
    assert_compound_case_is_grounded()
    for question in TEST_CASES:
        print_case(question)


if __name__ == "__main__":
    main()
