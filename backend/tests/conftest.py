"""Shared pytest fixtures and path setup for backend tests.

Two jobs:

1. Make the ``backend/`` modules importable as top-level names (the app uses
   ``from vector_store import ...`` rather than ``backend.vector_store``).
2. Provide reusable fixtures — sample data, a mocked ``RAGSystem``, and a
   FastAPI app + ``TestClient`` for exercising the HTTP endpoints.

Why the API app is built inline here instead of importing ``backend/app.py``:
the production module mounts the ``../frontend`` static directory *at import
time* (StaticFiles raises if the directory is missing) and constructs a real
``RAGSystem`` (which loads an embedding model and opens ChromaDB). Neither is
available or desirable under test. The ``test_app`` fixture rebuilds the same
routes against a mocked RAG system and a throwaway static directory, so the
endpoints can be tested in isolation without those import-time side effects.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

# Make the `backend/` modules importable as top-level names.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# --------------------------------------------------------------------------
# Sample data fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def sample_sources():
    """A representative citation list, mixing a linked and an unlinked source."""
    return [
        {
            "label": "Intro to RAG - Lesson 2",
            "url": "https://example.com/intro-rag/lesson-2",
        },
        {"label": "MCP Course - Lesson 1", "url": None},
    ]


@pytest.fixture
def sample_answer():
    """The answer text a RAGSystem.query would produce."""
    return "Chunking splits long text into smaller, embeddable pieces."


@pytest.fixture
def sample_query_response(sample_answer, sample_sources):
    """The ``(answer, sources)`` tuple RAGSystem.query returns."""
    return (sample_answer, sample_sources)


@pytest.fixture
def sample_course_stats():
    """Canned analytics matching RAGSystem.get_course_analytics()."""
    return {
        "total_courses": 2,
        "course_titles": ["Intro to RAG", "MCP Course"],
    }


# --------------------------------------------------------------------------
# Mocked RAG system
# --------------------------------------------------------------------------

@pytest.fixture
def mock_rag_system(sample_query_response, sample_course_stats):
    """A MagicMock standing in for ``RAGSystem`` with sensible defaults.

    - ``query(...)`` returns the canned ``(answer, sources)`` tuple.
    - ``session_manager.create_session()`` returns a stable id.
    - ``get_course_analytics()`` returns the canned stats dict.

    Tests can override any attribute (e.g. set ``query.side_effect``) before
    issuing a request through the ``client`` fixture.
    """
    rag = MagicMock()
    rag.query.return_value = sample_query_response
    rag.session_manager.create_session.return_value = "test-session-1"
    rag.get_course_analytics.return_value = sample_course_stats
    return rag


# --------------------------------------------------------------------------
# FastAPI app + test client
# --------------------------------------------------------------------------

@pytest.fixture
def test_app(mock_rag_system, tmp_path):
    """A FastAPI app mirroring ``backend/app.py`` but safe to import under test.

    The routes are defined inline against ``mock_rag_system`` so no real
    RAGSystem is built, and ``/`` is backed by a throwaway static directory
    instead of the (missing) ``../frontend``. The mock is exposed on
    ``app.state.rag_system`` for convenience.
    """
    from typing import List, Optional

    from fastapi import FastAPI, HTTPException
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    # Minimal frontend so mounting "/" succeeds and serves a real document.
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text(
        "<!doctype html><title>RAG</title><h1>Course Materials RAG</h1>",
        encoding="utf-8",
    )

    app = FastAPI(title="Course Materials RAG System (test)")

    # Request/response schemas mirror backend/app.py exactly.
    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class Source(BaseModel):
        label: str
        url: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[Source]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]

    class ClearSessionRequest(BaseModel):
        session_id: str

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()
            answer, sources = mock_rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:  # noqa: BLE001 - mirror app.py's blanket handler
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/session/clear")
    async def clear_session(request: ClearSessionRequest):
        try:
            mock_rag_system.session_manager.clear_session(request.session_id)
            return {"status": "ok"}
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e))

    # Mount the static frontend last so it doesn't shadow the /api routes.
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="static")

    app.state.rag_system = mock_rag_system
    return app


@pytest.fixture
def client(test_app):
    """A ``TestClient`` bound to the inline test app."""
    from fastapi.testclient import TestClient

    with TestClient(test_app) as test_client:
        yield test_client
