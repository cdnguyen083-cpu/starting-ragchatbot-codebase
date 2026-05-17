"""Tests that AIGenerator correctly invokes tools via the ToolManager."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_generator import AIGenerator
from search_tools import CourseSearchTool, ToolManager
from vector_store import SearchResults


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id, name, tool_input):
    return SimpleNamespace(
        type="tool_use", id=tool_id, name=name, input=tool_input
    )


def _make_response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _build_tool_manager_with_mock_store():
    store = MagicMock()
    store.search.return_value = SearchResults(
        documents=["Lesson body about MCP servers."],
        metadata=[{"course_title": "MCP Course", "lesson_number": 1}],
        distances=[0.1],
    )
    store.get_lesson_link.return_value = "https://example.com/mcp-l1"

    manager = ToolManager()
    manager.register_tool(CourseSearchTool(store))
    return manager, store


@patch("ai_generator.anthropic.Anthropic")
def test_generate_response_invokes_search_tool_and_returns_final_text(mock_anthropic):
    """A tool_use response must trigger ToolManager.execute_tool and a second LLM call."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    first = _make_response(
        content=[
            _tool_use_block(
                tool_id="toolu_1",
                name="search_course_content",
                tool_input={"query": "what are MCP servers"},
            )
        ],
        stop_reason="tool_use",
    )
    second = _make_response(
        content=[_text_block("MCP servers expose tools to language models.")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [first, second]

    tool_manager, store = _build_tool_manager_with_mock_store()
    gen = AIGenerator(api_key="test-key", model="claude-test")

    out = gen.generate_response(
        query="What are MCP servers?",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    # The tool was actually executed against the vector store
    store.search.assert_called_once_with(
        query="what are MCP servers", course_name=None, lesson_number=None
    )

    # Two API calls were made: one with tools, one with tool results
    assert mock_client.messages.create.call_count == 2
    first_call_kwargs = mock_client.messages.create.call_args_list[0].kwargs
    second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs

    assert "tools" in first_call_kwargs
    assert first_call_kwargs["tool_choice"] == {"type": "auto"}

    second_messages = second_call_kwargs["messages"]
    # user query, assistant tool_use, user tool_result
    assert len(second_messages) == 3
    assert second_messages[-1]["role"] == "user"
    tool_result_block = second_messages[-1]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "toolu_1"
    assert "MCP servers" in tool_result_block["content"] or "MCP Course" in tool_result_block["content"]

    # Final answer is the text from the second API call
    assert out == "MCP servers expose tools to language models."


@patch("ai_generator.anthropic.Anthropic")
def test_generate_response_without_tool_use_returns_direct_text(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        content=[_text_block("2 + 2 = 4")],
        stop_reason="end_turn",
    )

    gen = AIGenerator(api_key="test-key", model="claude-test")
    out = gen.generate_response(query="what is 2+2?")

    assert out == "2 + 2 = 4"
    # One API call only — no tool round-trip
    assert mock_client.messages.create.call_count == 1


@patch("ai_generator.anthropic.Anthropic")
def test_generate_response_passes_conversation_history_into_system(mock_anthropic):
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        content=[_text_block("ok")],
        stop_reason="end_turn",
    )

    gen = AIGenerator(api_key="test-key", model="claude-test")
    gen.generate_response(query="hi", conversation_history="User: hello\nAssistant: hi")

    system = mock_client.messages.create.call_args.kwargs["system"]
    assert "Previous conversation:" in system
    assert "User: hello" in system
