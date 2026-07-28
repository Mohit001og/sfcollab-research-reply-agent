"""Simple retrieval verification script."""

from __future__ import annotations

from retrieval import retrieve


TEST_QUERIES = [
    "How do I update my profile picture?",
    "Why can't I see more co-founder matches?",
    "I'm not getting email notifications",
    "What's the weather like today?",
    "Can you help me file my taxes?",
    "how do I delete my account and is that different from just deactivating it",
]


def print_results(query: str) -> None:
    """Print retrieval results for a single query."""
    print(f"QUERY: {query}")
    results = retrieve(query)
    if not results:
        print("NO MATCH")
    else:
        for result in results:
            print(f"- {result['title']} ({result['score']:.3f})")
    print()


def main() -> None:
    """Print retrieval results for a fixed set of test queries."""
    for query in TEST_QUERIES:
        print_results(query)


if __name__ == "__main__":
    main()
