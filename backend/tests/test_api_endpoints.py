"""Request/response tests for the FastAPI HTTP layer.

These exercise the endpoints defined by the ``test_app``/``client`` fixtures
in conftest.py — ``POST /api/query``, ``GET /api/courses``,
``POST /api/session/clear``, and the static ``/`` root — against a mocked
``RAGSystem``. The focus is the HTTP contract (status codes, payload shape,
validation, error mapping), not the RAG internals, which are covered by the
unit tests in the sibling modules.
"""
import pytest

# Every test in this module hits the HTTP API.
pytestmark = pytest.mark.api


# --------------------------------------------------------------------------
# POST /api/query
# --------------------------------------------------------------------------

class TestQueryEndpoint:
    def test_query_without_session_creates_one(self, client, mock_rag_system, sample_answer):
        resp = client.post("/api/query", json={"query": "What is chunking?"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == sample_answer
        # No session_id supplied -> the app asked the RAG system for a new one.
        assert body["session_id"] == "test-session-1"
        mock_rag_system.session_manager.create_session.assert_called_once_with()
        mock_rag_system.query.assert_called_once_with("What is chunking?", "test-session-1")

    def test_query_with_session_reuses_it(self, client, mock_rag_system):
        resp = client.post(
            "/api/query",
            json={"query": "follow-up", "session_id": "existing-42"},
        )

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "existing-42"
        # An existing session must NOT trigger creation of a new one.
        mock_rag_system.session_manager.create_session.assert_not_called()
        mock_rag_system.query.assert_called_once_with("follow-up", "existing-42")

    def test_query_returns_sources_in_response(self, client, sample_sources):
        body = client.post("/api/query", json={"query": "x"}).json()

        assert body["sources"] == sample_sources
        # Source objects keep their shape: a label and an (optional) url.
        first = body["sources"][0]
        assert set(first.keys()) == {"label", "url"}

    def test_query_missing_field_is_422(self, client):
        # Body has no "query" -> Pydantic validation error before our code runs.
        resp = client.post("/api/query", json={"session_id": "s1"})
        assert resp.status_code == 422

    def test_query_empty_body_is_422(self, client):
        resp = client.post("/api/query", json={})
        assert resp.status_code == 422

    def test_query_rag_failure_maps_to_500(self, client, mock_rag_system):
        mock_rag_system.query.side_effect = RuntimeError("vector store exploded")

        resp = client.post("/api/query", json={"query": "boom"})

        assert resp.status_code == 500
        assert "vector store exploded" in resp.json()["detail"]

    def test_query_accepts_empty_string_query(self, client, mock_rag_system):
        # An empty string is still a valid `str`; the endpoint should accept it
        # and delegate to the RAG system rather than 422.
        resp = client.post("/api/query", json={"query": ""})
        assert resp.status_code == 200
        mock_rag_system.query.assert_called_once_with("", "test-session-1")


# --------------------------------------------------------------------------
# GET /api/courses
# --------------------------------------------------------------------------

class TestCoursesEndpoint:
    def test_courses_returns_stats(self, client, sample_course_stats):
        resp = client.get("/api/courses")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_courses"] == sample_course_stats["total_courses"]
        assert body["course_titles"] == sample_course_stats["course_titles"]

    def test_courses_calls_analytics_once(self, client, mock_rag_system):
        client.get("/api/courses")
        mock_rag_system.get_course_analytics.assert_called_once_with()

    def test_courses_empty_catalog(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }
        body = client.get("/api/courses").json()
        assert body == {"total_courses": 0, "course_titles": []}

    def test_courses_failure_maps_to_500(self, client, mock_rag_system):
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("db down")

        resp = client.get("/api/courses")

        assert resp.status_code == 500
        assert "db down" in resp.json()["detail"]


# --------------------------------------------------------------------------
# POST /api/session/clear
# --------------------------------------------------------------------------

class TestSessionClearEndpoint:
    def test_clear_session_ok(self, client, mock_rag_system):
        resp = client.post("/api/session/clear", json={"session_id": "s1"})

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        mock_rag_system.session_manager.clear_session.assert_called_once_with("s1")

    def test_clear_session_missing_id_is_422(self, client):
        resp = client.post("/api/session/clear", json={})
        assert resp.status_code == 422

    def test_clear_session_failure_maps_to_500(self, client, mock_rag_system):
        mock_rag_system.session_manager.clear_session.side_effect = KeyError("nope")

        resp = client.post("/api/session/clear", json={"session_id": "ghost"})

        assert resp.status_code == 500


# --------------------------------------------------------------------------
# GET / (static frontend root)
# --------------------------------------------------------------------------

class TestRootEndpoint:
    def test_root_serves_frontend(self, client):
        resp = client.get("/")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Course Materials RAG" in resp.text

    def test_unknown_path_is_404(self, client):
        # Falls through the static mount with no matching file.
        assert client.get("/does-not-exist.html").status_code == 404


# --------------------------------------------------------------------------
# Cross-cutting
# --------------------------------------------------------------------------

class TestContentNegotiation:
    def test_query_rejects_non_json_body(self, client):
        resp = client.post(
            "/api/query",
            content="query=hello",
            headers={"content-type": "text/plain"},
        )
        assert resp.status_code == 422

    def test_courses_is_get_only(self, client):
        # POSTing to a GET-only route yields 405 Method Not Allowed.
        assert client.post("/api/courses").status_code == 405
