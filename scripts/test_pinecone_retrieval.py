"""Standalone smoke test for Pinecone-backed retrieval."""

from __future__ import annotations

from backend.retrieval_pinecone import retrieve


TEST_QUERIES = [
    "How do I update my profile picture?",  # direct match
    "What steps should I take to change the photo on my profile?",  # paraphrase
    "How do I updat my profle pictur?",  # misspelling
    "Can you help me with my account?",  # borderline / ambiguous
    "I have a question about settings",  # borderline / ambiguous
    "Something isn't working right",  # borderline / ambiguous
    "How does matching work?",  # borderline / ambiguous
    "What's the capital of France?",  # off-topic
    "Tell me a joke",  # off-topic
    "How do I bake a cake?",  # off-topic
    "What time is it?",  # off-topic
    "What's the weather like today?",  # ambiguous / refusal
    "",  # empty query
]


def print_results(query: str) -> None:
    """Print retrieval results for a single query."""
    label = query if query else "[EMPTY QUERY]"
    print(f"QUERY: {label}")
    results = retrieve(query)
    if not results:
        print("NO MATCH")
    else:
        print(f"TOP SCORE: {results[0]['score']:.3f}")
        for result in results:
            print(f"- {result['title']} ({result['score']:.3f})")
    print()


def main() -> None:
    """Run a small retrieval stress test against Pinecone."""
    for query in TEST_QUERIES:
        print_results(query)


if __name__ == "__main__":
    main()
