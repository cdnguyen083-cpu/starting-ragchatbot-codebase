import anthropic
from typing import List, Optional, Dict, Any, Tuple


class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""

    MAX_TOOL_ROUNDS = 2

    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to tools for course information.

Tool Selection:
- **get_course_outline**: Use for questions about a course's outline, syllabus, structure, table of contents, or list of lessons.
- **search_course_content**: Use for questions about specific material *inside* lessons.

Tool Usage:
- Use a tool only for questions about specific course content, structure, or detailed educational materials
- You may call tools across up to two sequential rounds: round 1 to gather initial information, round 2 to refine or look up follow-ups based on what round 1 returned (e.g., get_course_outline to find a lesson number, then search_course_content within it)
- Prefer a single round when one tool call is sufficient; only use a second round when the first result genuinely requires follow-up
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without calling tools
- **Course-specific questions**: Call the appropriate tool first, then answer
- **Outline questions**: Use get_course_outline, then present the course title, instructor, and a numbered list of lessons exactly as returned
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, tool explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800,
        }

        # Sources accumulated during the most recent generate_response call.
        # Read by RAGSystem after each query; reset at the top of every call.
        self.last_call_sources: List[Dict[str, Optional[str]]] = []

    def generate_response(self, query: str,
                          conversation_history: Optional[str] = None,
                          tools: Optional[List] = None,
                          tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Supports up to MAX_TOOL_ROUNDS sequential rounds of tool execution. Tools
        remain attached across rounds so Claude can chain calls (e.g., outline ->
        search). After the cap is reached, or when a tool execution raises, a
        final tool-less synthesis call forces Claude to emit text.
        """
        # Reset per-call source accumulator and any stale per-tool source state.
        self.last_call_sources = []
        if tool_manager is not None and hasattr(tool_manager, "reset_sources"):
            tool_manager.reset_sources()

        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        api_params: Dict[str, Any] = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content,
        }
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}

        response = self.client.messages.create(**api_params)

        for _ in range(self.MAX_TOOL_ROUNDS):
            if response.stop_reason != "tool_use" or tool_manager is None:
                return self._extract_text(response)

            api_params["messages"].append(
                {"role": "assistant", "content": response.content}
            )

            tool_results, had_error = self._execute_tools(response, tool_manager)
            api_params["messages"].append(
                {"role": "user", "content": tool_results}
            )

            if had_error:
                return self._finalize_without_tools(api_params)

            response = self.client.messages.create(**api_params)

        # Cap reached. If Claude still wants tools, force a tool-less synthesis.
        if response.stop_reason == "tool_use" and tool_manager is not None:
            return self._finalize_without_tools(api_params)
        return self._extract_text(response)

    def _execute_tools(self, response, tool_manager) -> Tuple[List[Dict[str, Any]], bool]:
        """Run every tool_use block in response.content. Returns (tool_results, had_error)."""
        tool_results: List[Dict[str, Any]] = []
        had_error = False
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            try:
                result = tool_manager.execute_tool(block.name, **block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
                self._accumulate_sources_from(tool_manager, block.name)
            except Exception as exc:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Tool error: {exc}",
                    "is_error": True,
                })
                had_error = True
        return tool_results, had_error

    def _accumulate_sources_from(self, tool_manager, tool_name: str) -> None:
        tools = getattr(tool_manager, "tools", None)
        if not tools:
            return
        tool_obj = tools.get(tool_name)
        new_sources = getattr(tool_obj, "last_sources", None)
        if not new_sources:
            return
        seen = {
            (s.get("label"), s.get("url")) for s in self.last_call_sources
        }
        for src in new_sources:
            key = (src.get("label"), src.get("url"))
            if key not in seen:
                self.last_call_sources.append(src)
                seen.add(key)

    def _finalize_without_tools(self, api_params: Dict[str, Any]) -> str:
        final_params = {
            k: v for k, v in api_params.items() if k not in ("tools", "tool_choice")
        }
        final_response = self.client.messages.create(**final_params)
        return self._extract_text(final_response)

    @staticmethod
    def _extract_text(response) -> str:
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return "I wasn't able to generate a response for that question. Try rephrasing it."
