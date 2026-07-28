"""In-process API checks for the SFCollab FastAPI app."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.main import app


TEST_CASES = [
    "How do I update my profile picture?",
    "What's the weather like today?",
    "How do I update my profile picture and will it show up immediately to people I've already matched with?",
]


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
    with TestClient(app) as client:
        for question in TEST_CASES:
            run_case(client, question)


if __name__ == "__main__":
    main()
