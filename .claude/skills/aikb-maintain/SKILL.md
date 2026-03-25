---
name: aikb-maintain
description: "Use when maintaining, extending, or debugging the aikb codebase. Covers adding new providers, modifying the store facade, updating tests, and architectural decisions."
---

# aikb: Codebase Maintenance

Use this skill when modifying or extending the aikb package itself.

## Architecture

aikb has two main modules:

### `aikb/base.py` — CRUD layer

1. **Provider protocol** (`KnowledgeBaseProvider`) — structural typing via `Protocol`
2. **Store facade** (`KnowledgeFiles`) — `MutableMapping` wrapping any provider
3. **Factory functions** (`LocalKb`, `ClaudeProject`) — progressive disclosure entry points
4. **Collection mappings** (`ClaudeProjects`) — `Mapping` of names → `KnowledgeFiles`

### `aikb/sync.py` — Sync engine

Operates on any two `MutableMapping` instances (not coupled to base.py):

- **Hashing**: `content_hash()`, `snapshot()` — compute `{filename: hash}` from any store
- **Reconciliation**: `reconcile()` — three-way (with manifest) or two-way diff algorithm
- **Conflict resolution**: `resolve_conflicts()` with `ConflictPolicy` enum or custom callable
- **Propagation**: `propagate()` — execute classified actions against stores
- **High-level ops**: `push()`, `pull()`, `clone()`, `sync()`, `status()`
- **Manifest I/O**: `load_manifest()`, `save_manifest()` — JSON persistence

### `aikb/mcp_server.py` — MCP tools

FastMCP server exposing CRUD as tools (gated behind `aikb[mcp]`).

## Key files

| File | Purpose |
|------|---------|
| `aikb/base.py` | Protocol, KnowledgeFiles, all providers, ClaudeProjects, factories, helpers |
| `aikb/sync.py` | Sync engine: reconcile, push, pull, clone, sync, status, manifest I/O |
| `aikb/__init__.py` | Public API exports only |
| `aikb/mcp_server.py` | FastMCP server (gated behind `aikb[mcp]`) |
| `tests/test_aikb.py` | pytest suite for base.py |
| `tests/test_sync.py` | pytest suite for sync.py (all 7 reconciliation cases, propagation, high-level ops) |
| `pyproject.toml` | Build config, optional deps groups |

## Adding a new provider

1. Create a class in `aikb/base.py` implementing the four protocol methods:

```python
class NewPlatformProvider:
    def __init__(self, ...):
        ...

    def list_files(self, project_id: str) -> Iterator[str]:
        ...  # yield filenames

    def read_file(self, project_id: str, filename: str) -> str:
        ...  # return content or raise KeyError

    def upsert_file(self, project_id: str, filename: str, content: str) -> None:
        ...

    def delete_file(self, project_id: str, filename: str) -> None:
        ...  # raise KeyError if not found
```

2. Add a factory function below the existing ones:

```python
def NewPlatform(project_id: str, *, ...) -> KnowledgeFiles:
    return KnowledgeFiles(NewPlatformProvider(...), project_id=project_id)
```

3. Optionally add a collection Mapping (like `ClaudeProjects`) if the platform supports listing projects.

4. Export from `aikb/__init__.py`.
5. Add to the `_get_store` dispatch in `aikb/mcp_server.py`.
6. Add optional dep group in `pyproject.toml` if needed.
7. Add tests in `tests/test_aikb.py`.

The new provider automatically works with all sync functions — `push()`, `pull()`, `sync()`, etc. — since they operate on any `MutableMapping`.

## Design rules

- **Provider methods raise `KeyError`** on missing files, not `FileNotFoundError`.
- **`list_files` and `__iter__` yield** — never return lists.
- **Optional deps are lazy-imported** at method-call time, not at module import. Use `_check_dependency()` to give informative install hints.
- **`functools.cached_property`** for expensive client initialization (e.g., API clients, org ID resolution).
- **No inheritance required** for providers — the `KnowledgeBaseProvider` Protocol uses structural subtyping.
- All arguments after the first positional MUST be keyword-only.
- **Session key resolution** is handled by `_resolve_claude_session_key()` — don't duplicate this logic.
- **Sync engine is decoupled** from stores — `aikb/sync.py` only depends on `MutableMapping`, never imports `aikb/base.py`.

## Testing

```bash
pytest tests/ -v               # all tests
pytest tests/test_sync.py -v   # sync tests only
pytest --doctest-modules aikb/  # doctests
```

- `LocalFilesProvider` tests use the `tmp_path` fixture (no cleanup needed).
- Sync tests use plain `dict` as the primary store (fast, no I/O).
- Integration tests with `LocalKb` verify sync works with real stores.
- Provider tests for external platforms use `pytest.importorskip()`.
- Integration tests requiring real credentials should be marked `@pytest.mark.integration`.
- Use `monkeypatch.setenv` / `monkeypatch.delenv` for env var tests.

## MCP server

The MCP server is a thin dispatch layer. When adding a new platform:
1. Add an `elif` branch to `_get_store()` in `mcp_server.py`
2. The tool functions themselves don't change — they delegate to `_get_store()`
3. For `"local"` platform, the project string is used as `project_id` (subfolder under default dir)
