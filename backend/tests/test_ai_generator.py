"""Tests that AIGenerator correctly handles 1-2 sequential rounds of tool use."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_generator import AIGenerator
from search_tools import CourseOutlineTool, CourseSearchTool, ToolManager
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


def _build_tool_manager_with_outline_and_search():
    store = MagicMock()
    store.search.return_value = SearchResults(
        documents=["Body about prompt caching."],
        metadata=[{"course_title": "Prompt Caching Course", "lesson_number": 2}],
        distances=[0.1],
    )
    store.get_lesson_link.return_value = "https://example.com/pc-l2"
    store._resolve_course_name.return_value = "MCP Course"
    store.course_catalog.get.return_value = {
        "metadatas": [{
            "instructor": "Alice",
            "course_link": "https://example.com/mcp",
            "lessons_json": (
                '[{"lesson_number": 4, "lesson_title": "Prompt Caching",'
                ' "lesson_link": "https://example.com/mcp-l4"}]'
            ),
        }]
    }

    manager = ToolManager()
    manager.register_tool(CourseSearchTool(store))
    manager.register_tool(CourseOutlineTool(store))
    return manager, store


@patch("ai_generator.anthropic.Anthropic")
def test_generate_response_invokes_search_tool_and_returns_final_text(mock_anthropic):
    """A single-round tool_use response triggers execute_tool and a second LLM call."""
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

    store.search.assert_called_once_with(
        query="what are MCP servers", course_name=None, lesson_number=None
    )

    assert mock_client.messages.create.call_count == 2
    first_call_kwargs = mock_client.messages.create.call_args_list[0].kwargs
    second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs

    assert "tools" in first_call_kwargs
    assert first_call_kwargs["tool_choice"] == {"type": "auto"}

    # Tools must remain attached on the second-round call so Claude can chain.
    assert "tools" in second_call_kwargs
    assert second_call_kwargs["tool_choice"] == {"type": "auto"}

    second_messages = second_call_kwargs["messages"]
    assert len(second_messages) == 3
    assert second_messages[-1]["role"] == "user"
    tool_result_block = second_messages[-1]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "toolu_1"
    assert "MCP servers" in tool_result_block["content"] or "MCP Course" in tool_result_block["content"]

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


@patch("ai_generator.anthropic.Anthropic")
def test_two_round_outline_then_search_chains_tools(mock_anthropic):
    """Round 1 outline -> round 2 search -> round 3 text. Two tool executions, three API calls."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    first = _make_response(
        content=[_tool_use_block("t1", "get_course_outline", {"course_name": "MCP"})],
        stop_reason="tool_use",
    )
    second = _make_response(
        content=[_tool_use_block(
            "t2", "search_course_content",
            {"query": "Prompt Caching"},
        )],
        stop_reason="tool_use",
    )
    third = _make_response(
        content=[_text_block("The Prompt Caching course discusses the same topic.")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [first, second, third]

    tool_manager, store = _build_tool_manager_with_outline_and_search()
    gen = AIGenerator(api_key="test-key", model="claude-test")

    out = gen.generate_response(
        query="Find a course on the same topic as lesson 4 of MCP",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    assert mock_client.messages.create.call_count == 3
    # Outline lookup + content search both happened
    store._resolve_course_name.assert_called_once_with("MCP")
    store.search.assert_called_once_with(
        query="Prompt Caching", course_name=None, lesson_number=None
    )

    # MagicMock captures references to the mutated messages list, so all
    # call_args_list entries reflect its final state. Assert the final shape:
    # user, asst tool_use 1, user tool_result 1, asst tool_use 2, user tool_result 2.
    final_messages = mock_client.messages.create.call_args_list[2].kwargs["messages"]
    assert [m["role"] for m in final_messages] == [
        "user", "assistant", "user", "assistant", "user"
    ]
    assert final_messages[2]["content"][0]["tool_use_id"] == "t1"
    assert final_messages[4]["content"][0]["tool_use_id"] == "t2"

    # Round 3 was made because round-2 response was tool_use, so tools still attached.
    third_kwargs = mock_client.messages.create.call_args_list[2].kwargs
    assert "tools" in third_kwargs
    assert third_kwargs["tool_choice"] == {"type": "auto"}

    assert out == "The Prompt Caching course discusses the same topic."


@patch("ai_generator.anthropic.Anthropic")
def test_max_rounds_overflow_forces_toolless_synthesis_call(mock_anthropic):
    """If Claude keeps requesting tools past the 2-round cap, a 4th tool-less call forces text."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    tu_a = _make_response(
        content=[_tool_use_block("t1", "search_course_content", {"query": "a"})],
        stop_reason="tool_use",
    )
    tu_b = _make_response(
        content=[_tool_use_block("t2", "search_course_content", {"query": "b"})],
        stop_reason="tool_use",
    )
    tu_c = _make_response(
        content=[_tool_use_block("t3", "search_course_content", {"query": "c"})],
        stop_reason="tool_use",
    )
    final = _make_response(
        content=[_text_block("final")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [tu_a, tu_b, tu_c, final]

    tool_manager, store = _build_tool_manager_with_mock_store()
    gen = AIGenerator(api_key="test-key", model="claude-test")

    out = gen.generate_response(
        query="anything",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    assert mock_client.messages.create.call_count == 4
    # Tools executed exactly twice (round-3 tool_use is discarded).
    assert store.search.call_count == 2

    fourth_kwargs = mock_client.messages.create.call_args_list[3].kwargs
    assert "tools" not in fourth_kwargs
    assert "tool_choice" not in fourth_kwargs
    assert out == "final"


@patch("ai_generator.anthropic.Anthropic")
def test_tools_remain_attached_on_second_round_call(mock_anthropic):
    """Regression guard: don't strip tools when sending the post-round-1 call."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _make_response(
            content=[_tool_use_block("t1", "search_course_content", {"query": "x"})],
            stop_reason="tool_use",
        ),
        _make_response(content=[_text_block("done")], stop_reason="end_turn"),
    ]

    tool_manager, _ = _build_tool_manager_with_mock_store()
    gen = AIGenerator(api_key="test-key", model="claude-test")

    gen.generate_response(
        query="q",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    first_kwargs = mock_client.messages.create.call_args_list[0].kwargs
    second_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    assert second_kwargs["tools"] == first_kwargs["tools"]
    assert second_kwargs["tool_choice"] == {"type": "auto"}


@patch("ai_generator.anthropic.Anthropic")
def test_tool_execution_exception_triggers_toolless_recovery_call(mock_anthropic):
    """A raising tool yields a tool_result(is_error=True) and one tool-less recovery call."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _make_response(
            content=[_tool_use_block("t1", "search_course_content", {"query": "x"})],
            stop_reason="tool_use",
        ),
        _make_response(
            content=[_text_block("Sorry, search failed.")],
            stop_reason="end_turn",
        ),
    ]

    tool_manager = MagicMock()
    tool_manager.tools = {}
    tool_manager.get_tool_definitions.return_value = []
    tool_manager.execute_tool.side_effect = RuntimeError("boom")

    gen = AIGenerator(api_key="test-key", model="claude-test")

    out = gen.generate_response(
        query="q",
        tools=[{"name": "search_course_content"}],
        tool_manager=tool_manager,
    )

    assert mock_client.messages.create.call_count == 2

    second_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    assert "tools" not in second_kwargs
    assert "tool_choice" not in second_kwargs

    err_block = second_kwargs["messages"][-1]["content"][0]
    assert err_block["type"] == "tool_result"
    assert err_block["tool_use_id"] == "t1"
    assert err_block.get("is_error") is True
    assert "boom" in err_block["content"]

    assert out == "Sorry, search failed."


@patch("ai_generator.anthropic.Anthropic")
def test_round_two_no_tool_use_returns_round_two_text(mock_anthropic):
    """1-round happy path: tool_use then text -> 2 API calls, return round-2 text."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _make_response(
            content=[_tool_use_block("t1", "search_course_content", {"query": "x"})],
            stop_reason="tool_use",
        ),
        _make_response(content=[_text_block("answer")], stop_reason="end_turn"),
    ]

    tool_manager, store = _build_tool_manager_with_mock_store()
    gen = AIGenerator(api_key="test-key", model="claude-test")

    out = gen.generate_response(
        query="q",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    assert mock_client.messages.create.call_count == 2
    assert store.search.call_count == 1
    assert out == "answer"


@patch("ai_generator.anthropic.Anthropic")
def test_no_tool_manager_skips_tool_handling(mock_anthropic):
    """Without a tool_manager, even a tool_use response is returned as-is (or fallback)."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response(
        content=[
            _text_block("partial"),
            _tool_use_block("t1", "search_course_content", {"query": "x"}),
        ],
        stop_reason="tool_use",
    )

    gen = AIGenerator(api_key="test-key", model="claude-test")
    out = gen.generate_response(query="q", tools=None, tool_manager=None)

    assert mock_client.messages.create.call_count == 1
    assert out == "partial"


@patch("ai_generator.anthropic.Anthropic")
def test_last_call_sources_accumulates_across_rounds_with_dedup(mock_anthropic):
    """Round-1 and round-2 sources are both surfaced, dedup'd by (label, url)."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    # First round returns lesson 1 sources; second round returns lesson 2 sources.
    store = MagicMock()
    store.search.side_effect = [
        SearchResults(
            documents=["Body A."],
            metadata=[{"course_title": "MCP Course", "lesson_number": 1}],
            distances=[0.1],
        ),
        SearchResults(
            documents=["Body B."],
            metadata=[{"course_title": "MCP Course", "lesson_number": 2}],
            distances=[0.1],
        ),
    ]
    store.get_lesson_link.side_effect = lambda title, n: f"https://example.com/mcp-l{n}"

    tool_manager = ToolManager()
    tool_manager.register_tool(CourseSearchTool(store))

    mock_client.messages.create.side_effect = [
        _make_response(
            content=[_tool_use_block("t1", "search_course_content", {"query": "a"})],
            stop_reason="tool_use",
        ),
        _make_response(
            content=[_tool_use_block("t2", "search_course_content", {"query": "b"})],
            stop_reason="tool_use",
        ),
        _make_response(content=[_text_block("done")], stop_reason="end_turn"),
    ]

    gen = AIGenerator(api_key="test-key", model="claude-test")
    gen.generate_response(
        query="q",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    labels = [s["label"] for s in gen.last_call_sources]
    assert labels == ["MCP Course - Lesson 1", "MCP Course - Lesson 2"]


@patch("ai_generator.anthropic.Anthropic")
def test_last_call_sources_dedups_identical_sources_across_rounds(mock_anthropic):
    """If both rounds return the same (label, url), it appears once."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    store = MagicMock()
    same_result = SearchResults(
        documents=["Body."],
        metadata=[{"course_title": "MCP Course", "lesson_number": 1}],
        distances=[0.1],
    )
    store.search.side_effect = [same_result, same_result]
    store.get_lesson_link.return_value = "https://example.com/mcp-l1"

    tool_manager = ToolManager()
    tool_manager.register_tool(CourseSearchTool(store))

    mock_client.messages.create.side_effect = [
        _make_response(
            content=[_tool_use_block("t1", "search_course_content", {"query": "a"})],
            stop_reason="tool_use",
        ),
        _make_response(
            content=[_tool_use_block("t2", "search_course_content", {"query": "b"})],
            stop_reason="tool_use",
        ),
        _make_response(content=[_text_block("done")], stop_reason="end_turn"),
    ]

    gen = AIGenerator(api_key="test-key", model="claude-test")
    gen.generate_response(
        query="q",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )

    assert len(gen.last_call_sources) == 1
    assert gen.last_call_sources[0]["label"] == "MCP Course - Lesson 1"


@patch("ai_generator.anthropic.Anthropic")
def test_last_call_sources_reset_between_calls(mock_anthropic):
    """A second call on the same AIGenerator must not leak sources from the first."""
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client

    tool_manager, _ = _build_tool_manager_with_mock_store()
    gen = AIGenerator(api_key="test-key", model="claude-test")

    # First call: one tool round, sources populated.
    mock_client.messages.create.side_effect = [
        _make_response(
            content=[_tool_use_block("t1", "search_course_content", {"query": "x"})],
            stop_reason="tool_use",
        ),
        _make_response(content=[_text_block("first")], stop_reason="end_turn"),
    ]
    gen.generate_response(
        query="q1",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )
    assert len(gen.last_call_sources) > 0

    # Second call: pure text response, no tools used.
    mock_client.messages.create.side_effect = [
        _make_response(content=[_text_block("second")], stop_reason="end_turn"),
    ]
    gen.generate_response(
        query="q2",
        tools=tool_manager.get_tool_definitions(),
        tool_manager=tool_manager,
    )
    assert gen.last_call_sources == []
