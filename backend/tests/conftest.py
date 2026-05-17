"""Shared pytest fixtures and path setup for backend tests."""
import os
import sys

# Make the `backend/` modules importable as top-level names
# (the application uses `from vector_store import ...` rather than `backend.vector_store`).
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
