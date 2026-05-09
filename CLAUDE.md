# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

This project uses **uv** as the package manager. Always invoke Python and tools through `uv` — never call `pip` or a bare `python`/`uvicorn` directly.

- Install / sync dependencies: `uv sync`
- Run the app (dev server with auto-reload): `cd backend && uv run uvicorn app:app --reload --port 8000`
  - Or use `./run.sh` (bash; on Windows run via Git Bash)
- Web UI: http://localhost:8000 — API docs: http://localhost:8000/docs

`.env` must contain `ANTHROPIC_API_KEY=...` at the repo root. `python-dotenv` loads it from [backend/config.py](backend/config.py).

There is no test suite configured. The top-level [main.py](main.py) is a stub (`print("Hello…")`) and is not the entry point — `backend/app.py` is.

## Architecture

This is a **tool-using RAG system**: the LLM decides whether to search and what to search for, rather than the backend retrieving and stuffing context unconditionally. Understanding this control flow is the key to working in this repo.

### Request lifecycle (single query)

1. Frontend [frontend/script.js](frontend/script.js) POSTs `{query, session_id}` to `/api/query` ([backend/app.py:56](backend/app.py#L56)).
2. [RAGSystem.query()](backend/rag_system.py#L102) loads conversation history from `SessionManager` and calls `AIGenerator.generate_response()` with the registered tool definitions.
3. [AIGenerator](backend/ai_generator.py) sends the prompt + tools to Claude. If `stop_reason == "tool_use"`, it executes the tool calls via `ToolManager`, appends results, and makes a **second** Claude call without tools to get the final answer. The system prompt enforces "one tool call per query maximum".
4. Two tools are registered ([backend/search_tools.py](backend/search_tools.py)):
   - **`search_course_content`** ([CourseSearchTool](backend/search_tools.py#L20)) — semantic search over lesson chunks. Calls `VectorStore.search()`, which (a) fuzzy-resolves the course name against `course_catalog`, then (b) queries `course_content` with optional `course_title` / `lesson_number` filters.
   - **`get_course_outline`** ([CourseOutlineTool](backend/search_tools.py#L116)) — fetches title + instructor + ordered lesson list directly from `course_catalog` metadata. Use this for outline/syllabus questions; do **not** make Claude search content for them (the chunks don't contain the word "outline").
5. After the answer is returned, sources are pulled from `tool_manager.get_last_sources()` (which inspects each tool's `last_sources` attribute) and **then reset**. Sources flow out-of-band — they are not part of the LLM's text.
6. The exchange is appended to session history; truncated to `MAX_HISTORY * 2` messages.

### Two ChromaDB collections (don't conflate them)

- `course_catalog`: one document per course, embedding the course title. Used for **fuzzy course-name resolution** before any content search. Lessons are stored as a JSON-serialized string in metadata (`lessons_json`) because ChromaDB metadata can't hold nested structures.
- `course_content`: one document per chunk. Filtered by `course_title` (the resolved title from step above) and/or `lesson_number`.

Course `title` is the primary key everywhere — it's used as the ChromaDB ID in the catalog and as the filter value for content. Two courses with the same title would collide.

### Document ingestion

[DocumentProcessor.process_course_document()](backend/document_processor.py#L97) expects a specific format:

```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <lesson title>
Lesson Link: <url>
<lesson body...>
Lesson 1: <next lesson title>
...
```

Chunks are sentence-aware with configurable overlap ([config.py](backend/config.py): `CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`). The first chunk of each lesson is prefixed with `"Lesson N content: "` (and last-lesson chunks include the course title) so the embedding carries lesson context. If you change chunking logic, this prefix convention is load-bearing for retrieval quality.

On startup ([app.py:88](backend/app.py#L88)), the app auto-loads `../docs` relative to `backend/` and **skips courses whose title already exists** in the catalog — re-running does not re-ingest. To force a rebuild, call `add_course_folder(..., clear_existing=True)` or delete `backend/chroma_db/`.

### Adding a new tool

Subclass [Tool](backend/search_tools.py#L6) (`get_tool_definition` + `execute`), register it in [RAGSystem.__init__](backend/rag_system.py#L13) via `tool_manager.register_tool(...)`. If the tool produces user-visible sources, expose a `last_sources` list attribute — `ToolManager.get_last_sources()` discovers it duck-typed.

### Configuration knobs

All in [backend/config.py](backend/config.py) as a frozen dataclass:
- `ANTHROPIC_MODEL = "claude-sonnet-4-6"` — change here, not in `ai_generator.py`.
- `EMBEDDING_MODEL = "all-MiniLM-L6-v2"` (sentence-transformers, runs locally).
- `MAX_RESULTS = 5`, `MAX_HISTORY = 2` (conversation turns kept), `CHROMA_PATH = "./chroma_db"` (relative to `backend/` cwd).

### Frontend

Static HTML/JS/CSS served by FastAPI's `StaticFiles` from `../frontend`. A `DevStaticFiles` subclass injects no-cache headers so edits to JS/CSS show up on reload without a hard refresh.
