"""Coordinator FastAPI entrypoint. Graph and API handlers remain in workflow.py for behavior-preserving migration."""
from app.graphs.workflow import app

__all__ = ["app"]
