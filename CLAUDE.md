# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- **Run app** (from repo root, Git Bash on Windows): `./run.sh`
- **Run app manually**: `cd backend && uv run uvicorn app:app --reload --port 8000`
- **Install / sync deps**: `uv sync`
- **Required env var**: `ANTHROPIC_API_KEY` in `.env` at repo root (copy from `.env.example`)
- **URLs once running**: web UI at `http://localhost:8000`, OpenAPI docs at `http://localhost:8000/docs`

No test suite, linter, or formatter is configured in this repo — don't invent commands for them.

**Tooling rule:** always use `uv run` to execute Python in this repo. Never invoke `python`, `pip`, or `pip install` directly.

## Architecture

FastAPI app in [backend/app.py](backend/app.py) instantiates a single `RAGSystem` ([backend/rag_system.py](backend/rag_system.py)) at startup and exposes `POST /api/query` and `GET /api/courses`. On startup it ingests `../docs` (relative to `backend/`). The frontend is plain HTML/JS served by FastAPI at `/` from `../frontend`.

Component responsibilities (each is its own file in [backend/](backend/)):

- **`DocumentProcessor`** ([backend/document_processor.py](backend/document_processor.py)) — parses course `.txt` docs with header format `Course Title:` / `Course Link:` / `Course Instructor:` followed by `Lesson N: <title>` blocks (optionally `Lesson Link:` on the next line). Sentence-aware chunking using `CHUNK_SIZE=800` / `CHUNK_OVERLAP=100`; lesson chunks are prefixed with `Course <title> Lesson <n> content:` to give the embedding lexical context.
- **`VectorStore`** ([backend/vector_store.py](backend/vector_store.py)) — ChromaDB persistent client at `./chroma_db` (relative to CWD). Two collections: `course_catalog` (one doc per course, used to fuzzy-resolve a `course_name` argument to a canonical title via vector search) and `course_content` (chunked lesson text with `course_title` / `lesson_number` / `chunk_index` metadata, filtered with `$and` when both course and lesson are specified). Embeddings: `all-MiniLM-L6-v2` via sentence-transformers.
- **`AIGenerator`** ([backend/ai_generator.py](backend/ai_generator.py)) — wraps the Anthropic SDK. Calls Claude with `tool_choice=auto`; if `stop_reason == "tool_use"`, executes tools via the `ToolManager`, appends results, and makes a second (tool-less) call for the final answer. **One round of tool use only** — the system prompt also tells the model "One search per query maximum."
- **`ToolManager` + `CourseSearchTool`** ([backend/search_tools.py](backend/search_tools.py)) — `Tool` ABC pattern. `CourseSearchTool` exposes `search_course_content(query, course_name?, lesson_number?)` to Claude and stashes its source list on `self.last_sources` so the API response can return citations after the tool call completes. `RAGSystem.query` reads then resets sources after each query.
- **`SessionManager`** ([backend/session_manager.py](backend/session_manager.py)) — in-memory dict of `session_id → List[Message]`. `MAX_HISTORY=2` exchanges (4 messages) are kept and formatted into the system prompt. Sessions are lost on restart.
- **`Config`** ([backend/config.py](backend/config.py)) — single dataclass; default model is `claude-sonnet-4-20250514`.

## Non-obvious constraints

- **Server must be started from `backend/`.** The app uses CWD-relative paths for the docs folder (`../docs`), static mount (`../frontend`), and ChromaDB store (`./chroma_db`). Running `uvicorn` from the repo root will silently break document ingestion and 404 the frontend. `run.sh` handles this with `cd backend && uv run uvicorn ...`.
- **On Windows, run `run.sh` from Git Bash**, not PowerShell or CMD (per [README.md](README.md)).
- **Document ingestion is incremental by title.** `RAGSystem.add_course_folder` skips files whose `Course Title:` already exists in `course_catalog`. To force a rebuild, pass `clear_existing=True` or delete `backend/chroma_db/`.
- **Course identity is the title string**, used as both the ChromaDB id and the join key between `course_catalog` and `course_content`. Renaming a course title in a source doc creates a duplicate course rather than updating the existing one.
- **Tool sources are returned out-of-band** from the LLM answer text. The frontend reads `sources` separately from `answer`; don't parse citations out of the answer text.
