"""End-to-end retrieval plus grounded generation verification."""

from __future__ import annotations

import os
from time import perf_counter
from types import SimpleNamespace

import backend.generation as generation
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
        result = generation.generate_draft_reply(question, retrieved)
        elapsed = perf_counter() - start
        print(f"ELAPSED: {elapsed:.3f}s")
        print(f"GROUNDED: {result['grounded']}")
        print("DRAFT:")
        print(result["draft"])
    except generation.GenerationError as exc:
        elapsed = perf_counter() - start
        print(f"ELAPSED: {elapsed:.3f}s")
        print(f"ERROR: {exc}")
    print()


def assert_compound_case_is_grounded() -> None:
    """Verify the validator allows a hedged partial answer through."""
    retrieved = retrieve(COMPOUND_QUESTION)
    result = generation.generate_draft_reply(COMPOUND_QUESTION, retrieved)
    assert retrieved, "Expected retrieval to return evidence for the compound question."
    assert result["grounded"] is True, "Expected the partial-answer draft to remain grounded."
    assert "I don't have enough information" not in result["draft"], "Expected an answer, not a refusal."


def test_generate_draft_reply_uses_groq_model_from_environment(monkeypatch) -> None:
    """Verify the configured model name is passed through to Groq."""
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="I don't have enough information in the help content to answer this confidently."
                        )
                    )
                ]
            )

    class FakeGroqClient:
        def __init__(self, api_key: str):
            captured["api_key"] = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.6-27b")
    monkeypatch.delenv("OFFLINE_TEST_MODE", raising=False)
    monkeypatch.setattr(generation, "Groq", FakeGroqClient)
    monkeypatch.setattr(generation, "_GROQ_IMPORT_ERROR", None)

    result = generation.generate_draft_reply(
        "How do I update my profile picture?",
        retrieve("How do I update my profile picture?"),
    )

    assert captured["api_key"] == "test-key"
    assert captured["model"] == "qwen/qwen3.6-27b"
    assert result["grounded"] is True


def test_generate_draft_reply_defaults_to_openai_gpt_oss_120b(monkeypatch) -> None:
    """Verify the fallback model is the new Groq default."""
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="I don't have enough information in the help content to answer this confidently."
                        )
                    )
                ]
            )

    class FakeGroqClient:
        def __init__(self, api_key: str):
            captured["api_key"] = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("OFFLINE_TEST_MODE", raising=False)
    monkeypatch.setattr(generation, "Groq", FakeGroqClient)
    monkeypatch.setattr(generation, "_GROQ_IMPORT_ERROR", None)

    result = generation.generate_draft_reply(
        "How do I update my profile picture?",
        retrieve("How do I update my profile picture?"),
    )

    assert captured["model"] == "openai/gpt-oss-120b"
    assert result["grounded"] is True


def main() -> None:
    """Run all end-to-end generation checks."""
    os.environ.setdefault("OFFLINE_TEST_MODE", "true")
    assert_compound_case_is_grounded()
    for question in TEST_CASES:
        print_case(question)


if __name__ == "__main__":
    main()
