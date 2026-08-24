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


def test_generic_greeting_is_not_grounded() -> None:
    """Reject a generic greeting when relevant evidence exists."""
    retrieved = [
        {
            "id": "profile-setup-02",
            "title": "How do I update my profile picture?",
            "content": (
                "Go to Profile Settings and open the photo section to upload a new image. "
                "We recommend a recent headshot with good lighting so match cards feel more trustworthy. "
                "If the upload fails, try a smaller JPG or PNG file and refresh the page before retrying."
            ),
            "score": 0.905,
        }
    ]

    assert generation._is_grounded_draft("Hi there! How can I help you today?", retrieved) is False


def test_exact_clarification_failure_is_not_grounded() -> None:
    """Reject a clarification-only response that is not an answer."""
    retrieved = [
        {
            "id": "profile-setup-02",
            "title": "How do I update my profile picture?",
            "content": (
                "Go to Profile Settings and open the photo section to upload a new image. "
                "We recommend a recent headshot with good lighting so match cards feel more trustworthy. "
                "If the upload fails, try a smaller JPG or PNG file and refresh the page before retrying."
            ),
            "score": 0.905,
        }
    ]

    assert generation._is_grounded_draft("Please provide the question you need help with.", retrieved) is False


def test_generic_clarification_is_not_grounded() -> None:
    """Reject a generic request for more details when evidence exists."""
    retrieved = [
        {
            "id": "profile-setup-02",
            "title": "How do I update my profile picture?",
            "content": (
                "Go to Profile Settings and open the photo section to upload a new image. "
                "We recommend a recent headshot with good lighting so match cards feel more trustworthy. "
                "If the upload fails, try a smaller JPG or PNG file and refresh the page before retrying."
            ),
            "score": 0.905,
        }
    ]

    assert generation._is_grounded_draft("Can you share more details about your question?", retrieved) is False


def test_legitimate_profile_picture_answer_is_grounded() -> None:
    """Accept a paraphrased answer that clearly uses the retrieved evidence."""
    retrieved = [
        {
            "id": "profile-setup-02",
            "title": "How do I update my profile picture?",
            "content": (
                "Go to Profile Settings and open the photo section to upload a new image. "
                "We recommend a recent headshot with good lighting so match cards feel more trustworthy. "
                "If the upload fails, try a smaller JPG or PNG file and refresh the page before retrying."
            ),
            "score": 0.905,
        }
    ]

    draft = (
        "Go to Profile Settings and open the photo section to upload a new image. "
        "If the upload fails, try a smaller JPG or PNG file."
    )

    assert generation._is_grounded_draft(draft, retrieved) is True


def test_answer_with_brief_clarification_request_is_still_grounded() -> None:
    """Allow a legitimate answer that also asks for clarification at the end."""
    retrieved = [
        {
            "id": "profile-setup-02",
            "title": "How do I update my profile picture?",
            "content": (
                "Go to Profile Settings and open the photo section to upload a new image. "
                "We recommend a recent headshot with good lighting so match cards feel more trustworthy. "
                "If the upload fails, try a smaller JPG or PNG file and refresh the page before retrying."
            ),
            "score": 0.905,
        }
    ]

    draft = (
        "Go to Profile Settings and open the photo section to upload a new image. "
        "If that still does not work, try a smaller JPG or PNG file. "
        "If you want, I can help you troubleshoot the upload."
    )

    assert generation._is_grounded_draft(draft, retrieved) is True


def test_generate_draft_reply_prompt_requires_direct_answer(monkeypatch) -> None:
    """Verify the request prompt tells Groq to answer directly from the supplied evidence."""
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                "Go to Profile Settings and open the photo section to upload a new image."
                            )
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

    generation.generate_draft_reply(
        "How do I update my profile picture?",
        retrieve("How do I update my profile picture?"),
    )

    prompt = captured["messages"][1]["content"]
    assert "Answer the user's question directly" in prompt
    assert "do not ask the user to provide the question" in prompt
    assert "Do not greet the user" in prompt
    assert "open the photo section to upload a new image" in prompt


def test_generate_draft_reply_retries_clarification_only_response(monkeypatch) -> None:
    """Verify a clarification-only first draft gets one corrective retry."""
    captured: dict[str, object] = {"calls": []}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["calls"].append(kwargs)
            if len(captured["calls"]) == 1:
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="Please let me know what you need help with."
                            )
                        )
                    ]
                )
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                "Go to Profile Settings and open the photo section to upload a new image."
                            )
                        )
                    )
                ]
            )

    class FakeGroqClient:
        def __init__(self, api_key: str):
            captured["api_key"] = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("OFFLINE_TEST_MODE", raising=False)
    monkeypatch.setattr(generation, "Groq", FakeGroqClient)
    monkeypatch.setattr(generation, "_GROQ_IMPORT_ERROR", None)

    result = generation.generate_draft_reply(
        "How do I update my profile picture?",
        retrieve("How do I update my profile picture?"),
    )

    assert len(captured["calls"]) == 2
    assert "Rewrite it now using only the provided evidence" in captured["calls"][1]["messages"][1]["content"]
    assert result["grounded"] is True
    assert result["draft"] == "Go to Profile Settings and open the photo section to upload a new image."


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
