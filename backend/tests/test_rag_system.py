"""End-to-end tests for RAGSystem.query handling of content questions.

We mock the Anthropic client and the VectorStore so the test is hermetic
and exercises the orchestration logic in `rag_system.py` plus the
real `ToolManager` + `CourseSearchTool` wiring.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config import Config
from rag_system import RAGSystem
from vector_store import SearchResults


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def _make_response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


@pytest.fixture
def fake_config(tmp_path):
    cfg = Config()
    cfg.ANTHROPIC_API_KEY = "test-key"
    cfg.ANTHROPIC_MODEL = "claude-test"
    cfg.CHROMA_PATH = str(tmp_path / "chroma_db_test")
    return cfg


def _install_fake_vector_store(rag, documents, metadata, lesson_link=None):
    """Replace the live VectorStore on a RAGSystem with a MagicMock."""
    fake = MagicMock()
    fake.search.return_value = SearchResults(
        documents=documents,
        metadata=metadata,
        distances=[0.1] * len(documents),
    )
    fake.get_lesson_link.return_value = lesson_link
    # Both tools hold their own reference — swap on each.
    rag.vector_store = fake
    rag.search_tool.store = fake
    rag.outline_tool.store = fake
    return fake


@patch("ai_generator.anthropic.Anthropic")
def test_query_routes_content_question_through_search_tool(mock_anthropic, fake_config):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Claude asks for search_course_content, then returns a final text answer
    mock_client.messages.create.side_effect = [
        _make_response(
            content=[
                _tool_use_block(
                    "toolu_1",
                    "search_course_content",
                    {"query": "what is chunking"},
                )
            ],
            stop_reason="tool_use",
        ),
        _make_response(
            content=[_text_block("Chunking splits long text into smaller pieces.")],
            stop_reason="end_turn",
        ),
    ]

    rag = RAGSystem(fake_config)
    store = _install_fake_vector_store(
        rag,
        documents=["Chunking splits text into ~800-char windows..."],
        metadata=[{"course_title": "Intro to RAG", "lesson_number": 2}],
        lesson_link="https://example.com/intro-rag/lesson-2",
    )

    answer, sources = rag.query("What is chunking?")

    # The vector store really got called with the LLM-supplied query
    store.search.assert_called_once_with(
        query="what is chunking", course_name=None, lesson_number=None
    )

    assert answer == "Chunking splits long text into smaller pieces."
    assert sources == [
        {
            "label": "Intro to RAG - Lesson 2",
            "url": "https://example.com/intro-rag/lesson-2",
        }
    ]


@patch("ai_generator.anthropic.Anthropic")
def test_sources_do_not_leak_between_queries(mock_anthropic, fake_config):
    """A query that doesn't search must not surface sources from a prior search."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # Call 1: search round + text. Call 2: pure text, no tools used.
    mock_client.messages.create.side_effect = [
        _make_response(
            content=[
                _tool_use_block("t1", "search_course_content", {"query": "q"})
            ],
            stop_reason="tool_use",
        ),
        _make_response(content=[_text_block("a")], stop_reason="end_turn"),
        _make_response(content=[_text_block("general")], stop_reason="end_turn"),
    ]

    rag = RAGSystem(fake_config)
    _install_fake_vector_store(
        rag,
        documents=["doc"],
        metadata=[{"course_title": "C", "lesson_number": 1}],
        lesson_link="u",
    )

    _, first_sources = rag.query("course-specific q")
    assert first_sources, "expected sources on first call"

    _, second_sources = rag.query("general-knowledge q")
    assert second_sources == [], (
        "second query did not search; sources from the first query must not leak"
    )


@patch("ai_generator.anthropic.Anthropic")
def test_query_returns_empty_sources_when_llm_does_not_use_a_tool(
    mock_anthropic, fake_config
):
    """General-knowledge questions should produce an answer with no source citations."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        content=[_text_block("Paris is the capital of France.")],
        stop_reason="end_turn",
    )

    rag = RAGSystem(fake_config)
    _install_fake_vector_store(
        rag, documents=[], metadata=[], lesson_link=None
    )

    answer, sources = rag.query("What is the capital of France?")
    assert answer == "Paris is the capital of France."
    assert sources == []


@patch("ai_generator.anthropic.Anthropic")
def test_query_propagates_session_history_into_llm_call(mock_anthropic, fake_config):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        content=[_text_block("ok")], stop_reason="end_turn"
    )

    rag = RAGSystem(fake_config)
    _install_fake_vector_store(rag, documents=[], metadata=[])

    session_id = rag.session_manager.create_session() if hasattr(
        rag.session_manager, "create_session"
    ) else "s1"
    # Pre-seed the session manager with history if the API supports it
    if hasattr(rag.session_manager, "add_exchange"):
        rag.session_manager.add_exchange(session_id, "earlier q", "earlier a")

    rag.query("follow-up question", session_id=session_id)

    system = mock_client.messages.create.call_args.kwargs["system"]
    assert "earlier q" in system or "Previous conversation:" in system
