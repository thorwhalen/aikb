"""MCP server exposing knowledge base CRUD as tools.

Requires ``pip install aikb[mcp]``.

Run with::

    python -m aikb.mcp_server
"""

from aikb.base import LocalKb, ClaudeProject, _check_dependency


def _get_store(platform: str, project: str):
    """Return a KnowledgeFiles store for the given platform and project."""
    if platform == "local":
        return LocalKb(project_id=project)
    elif platform == "claude":
        return ClaudeProject(project)
    else:
        raise ValueError(f"Unknown platform {platform!r}. Supported: 'local', 'claude'")


def create_server():
    """Create and return the FastMCP server instance."""
    _check_dependency("fastmcp", install_hint="Install with: pip install aikb[mcp]")
    from fastmcp import FastMCP

    mcp = FastMCP("aikb")

    @mcp.tool()
    def list_files(platform: str, project: str) -> list[str]:
        """List all knowledge files in a project."""
        store = _get_store(platform, project)
        return list(store)

    @mcp.tool()
    def read_file(platform: str, project: str, filename: str) -> str:
        """Read the contents of a knowledge file."""
        store = _get_store(platform, project)
        return store[filename]

    @mcp.tool()
    def write_file(platform: str, project: str, filename: str, content: str) -> dict:
        """Create or update a knowledge file."""
        store = _get_store(platform, project)
        store[filename] = content
        return {
            "status": "ok",
            "platform": platform,
            "project": project,
            "file": filename,
        }

    @mcp.tool()
    def delete_file(platform: str, project: str, filename: str) -> dict:
        """Delete a knowledge file."""
        store = _get_store(platform, project)
        del store[filename]
        return {
            "status": "ok",
            "platform": platform,
            "project": project,
            "file": filename,
        }

    return mcp


if __name__ == "__main__":
    server = create_server()
    server.run()
