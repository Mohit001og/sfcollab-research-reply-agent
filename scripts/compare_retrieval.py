"""Compare TF-IDF and Chroma retrieval results side by side."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.retrieval import retrieve as retrieve_tfidf
from backend.retrieval_chroma import retrieve as retrieve_chroma


TEST_QUERIES = [
    "How do I update my profile picture?",
    "Why can't I see more co-founder matches?",
    "I'm not getting email notifications",
    "What's the weather like today?",
    "Can you help me file my taxes?",
    "how do I delete my account and is that different from just deactivating it",
    "How do i updat my profle picture?",
    "",
]


def _format_results(results: list[dict[str, object]]) -> str:
    if not results:
        return "NO MATCH"
    return " | ".join(f"{item['title']} ({item['score']:.3f})" for item in results)


def main() -> None:
    for query in TEST_QUERIES:
        tfidf_results = retrieve_tfidf(query)
        chroma_results = retrieve_chroma(query)
        label = query if query else "<EMPTY QUERY>"
        print(f"QUERY: {label}")
        print(f"TF-IDF : {_format_results(tfidf_results)}")
        print(f"CHROMA : {_format_results(chroma_results)}")
        print()


if __name__ == "__main__":
    main()
