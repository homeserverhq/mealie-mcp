"""Semantic audit suite for the Mealie MCP server.

The suite is black-box: it talks JSON-RPC/SSE to a running server and never
imports the server implementation. See ``docs/tool-audit.md`` and the repo
README for how to run it.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
