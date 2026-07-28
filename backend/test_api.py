"""In-process API checks for the SFCollab FastAPI app."""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


TEST_CASES = [
    "How do I update my profile picture?",
    "What's the weather like today?",
    "How do I update my profile picture and will it show up immediately to people I've already matched with?",
]


def fake_generate_draft_reply(question: str, retrieved_snippets: list[dict[str, object]]) -> dict[str, object]:
    """Deterministic stand-in for Groq-backed generation during API tests."""
    if not retrieved_snippets:
        return {
            "draft": "I don't have enough information in the help content to answer this confidently.",
            "grounded": False,
        }

    if "matched with" in question:
        return {
            "draft": (
                "You can update your profile picture, but the snippets do not say whether the change appears "
                "immediately for people you already matched with."
            ),
            "grounded": True,
        }

    return {
        "draft": f"Grounded answer for: {question}",
        "grounded": True,
    }


def run_case(client: TestClient, question: str) -> None:
    """Call the ask endpoint and print the full JSON response."""
    response = client.post("/api/ask", json={"question": question})
    print(f"QUESTION: {question}")
    print(f"STATUS: {response.status_code}")
    print(json.dumps(response.json(), indent=2, sort_keys=True))
    print()
    assert response.status_code == 200


def main() -> None:
    """Run the endpoint checks in-process."""
    with patch("main.generate_draft_reply", side_effect=fake_generate_draft_reply):
        with TestClient(app) as client:
            for question in TEST_CASES:
                run_case(client, question)


if __name__ == "__main__":
    main()
