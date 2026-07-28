"""End-to-end retrieval plus grounded generation verification."""

from __future__ import annotations

from time import perf_counter

from backend.generation import GenerationError, generate_draft_reply
from backend.retrieval import retrieve


TEST_CASES = [
    "How do I update my profile picture?",
    "What's the weather like today?",
    "Can I use SFCollab if I'm not based in the US?",
    "How do I update my profile picture and will it show up immediately to people I've already matched with?",
]


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


def main() -> None:
    """Run all end-to-end generation checks."""
    for question in TEST_CASES:
        print_case(question)


if __name__ == "__main__":
    main()
