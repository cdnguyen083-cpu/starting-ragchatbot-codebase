"""Tests for CourseSearchTool.execute in backend/search_tools.py."""
from unittest.mock import MagicMock

from search_tools import CourseSearchTool
from vector_store import SearchResults


def _make_results(documents, metadata, distances=None, error=None):
    return SearchResults(
        documents=documents,
        metadata=metadata,
        distances=distances or [0.1] * len(documents),
        error=error,
    )


def test_execute_returns_formatted_results_with_lesson_header():
    store = MagicMock()
    store.search.return_value = _make_results(
        documents=["The quick brown fox jumps."],
        metadata=[{"course_title": "Intro to RAG", "lesson_number": 2}],
    )
    store.get_lesson_link.return_value = "https://example.com/lesson-2"

    tool = CourseSearchTool(store)
    out = tool.execute(query="fox")

    store.search.assert_called_once_with(
        query="fox", course_name=None, lesson_number=None
    )
    assert "[Intro to RAG - Lesson 2]" in out
    assert "The quick brown fox jumps." in out
    assert tool.last_sources == [
        {"label": "Intro to RAG - Lesson 2", "url": "https://example.com/lesson-2"}
    ]


def test_execute_passes_course_and_lesson_filters_to_store():
    store = MagicMock()
    store.search.return_value = _make_results(
        documents=["Lesson 3 body"],
        metadata=[{"course_title": "MCP Course", "lesson_number": 3}],
    )
    store.get_lesson_link.return_value = None

    tool = CourseSearchTool(store)
    tool.execute(query="anything", course_name="MCP", lesson_number=3)

    store.search.assert_called_once_with(
        query="anything", course_name="MCP", lesson_number=3
    )


def test_execute_returns_error_message_when_store_errors():
    store = MagicMock()
    store.search.return_value = _make_results(
        documents=[], metadata=[], error="Search error: boom"
    )

    tool = CourseSearchTool(store)
    out = tool.execute(query="x")

    assert out == "Search error: boom"
    # No sources should leak through on error.
    assert tool.last_sources == []


def test_execute_returns_friendly_message_when_no_results():
    store = MagicMock()
    store.search.return_value = _make_results(documents=[], metadata=[])

    tool = CourseSearchTool(store)
    out = tool.execute(query="x", course_name="MCP", lesson_number=4)

    assert "No relevant content found" in out
    assert "course 'MCP'" in out
    assert "lesson 4" in out


def test_execute_deduplicates_sources_for_chunks_from_same_lesson():
    """When ChromaDB returns multiple chunks from one lesson, the UI should
    receive a single citation, not one per chunk."""
    store = MagicMock()
    store.search.return_value = _make_results(
        documents=["chunk one", "chunk two"],
        metadata=[
            {"course_title": "MCP Course", "lesson_number": 1},
            {"course_title": "MCP Course", "lesson_number": 1},
        ],
    )
    store.get_lesson_link.return_value = "https://example.com/mcp/lesson-1"

    tool = CourseSearchTool(store)
    tool.execute(query="anything")

    # Both chunks still appear in the formatted text, but the source list
    # should have a single deduplicated entry per (course, lesson).
    assert tool.last_sources == [
        {"label": "MCP Course - Lesson 1", "url": "https://example.com/mcp/lesson-1"}
    ]


def test_execute_handles_missing_lesson_number_in_metadata():
    store = MagicMock()
    store.search.return_value = _make_results(
        documents=["Course-level intro paragraph"],
        metadata=[{"course_title": "Intro to RAG", "lesson_number": None}],
    )

    tool = CourseSearchTool(store)
    out = tool.execute(query="intro")

    # Header should not have a "Lesson N" suffix when lesson_number is None
    assert "[Intro to RAG]" in out
    # And get_lesson_link must not be invoked with a None lesson number
    store.get_lesson_link.assert_not_called()
    assert tool.last_sources == [
        {"label": "Intro to RAG", "url": None}
    ]
