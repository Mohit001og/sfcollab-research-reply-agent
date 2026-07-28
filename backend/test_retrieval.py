"""Simple retrieval verification script."""

from retrieval import retrieve


TEST_QUERIES = [
    "How do I update my profile picture?",
    "Why can't I see more co-founder matches?",
    "I'm not getting email notifications",
    "What's the weather like today?",
    "Can you help me file my taxes?",
]


def main() -> None:
    """Print retrieval results for a fixed set of test queries."""
    for query in TEST_QUERIES:
        print(f"QUERY: {query}")
        results = retrieve(query)
        if not results:
            print("NO MATCH")
        else:
            for result in results:
                print(f"- {result['title']} ({result['score']:.3f})")
        print()


if __name__ == "__main__":
    main()
