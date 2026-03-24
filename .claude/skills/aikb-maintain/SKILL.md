---
name: aikb-maintain
description: "Use when maintaining, extending, or debugging the aikb codebase. Covers adding new providers, modifying the store facade, updating tests, and architectural decisions."
---

# aikb: Codebase Maintenance

Use this skill when modifying or extending the aikb package itself.

## Architecture

aikb has three layers:

1. **Provider protocol** (`KnowledgeBaseProvider`) — structural typing via `Protocol`
2. **Store facade** (`KnowledgeFiles`) — `MutableMapping` wrapping any provider
3. **Factory functions** (`LocalFiles`, `ClaudeProject`) — progressive disclosure entry points

All core code lives in `aikb/base.py`. The MCP server is in `aikb/mcp_server.py`.

## Key files

| File | Purpose |
|------|---------|
| `aikb/base.py` | Protocol, KnowledgeFiles, all providers, KnowledgeMall, factories |
| `aikb/__init__.py` | Public API exports only |
| `aikb/mcp_server.py` | FastMCP server (gated behind `aikb[mcp]`) |
| `tests/test_aikb.py` | pytest suite |
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

3. Export from `aikb/__init__.py`.
4. Add to the `_get_store` dispatch in `aikb/mcp_server.py`.
5. Add optional dep group in `pyproject.toml` if needed.
6. Add tests in `tests/test_aikb.py`.

## Design rules

- **Provider methods raise `KeyError`** on missing files, not `FileNotFoundError`.
- **`list_files` and `__iter__` yield** — never return lists.
- **Optional deps are lazy-imported** at method-call time, not at module import. Use `_check_dependency()` to give informative install hints.
- **`functools.cached_property`** for expensive client initialization (e.g., API clients).
- **No inheritance required** for providers — the `KnowledgeBaseProvider` Protocol uses structural subtyping.
- All arguments after the first positional MUST be keyword-only.

## Testing

```bash
pytest tests/ -v               # unit tests
pytest --doctest-modules aikb/  # doctests
```

- `LocalFilesProvider` tests use the `tmp_path` fixture (no cleanup needed).
- Provider tests for external platforms use `pytest.importorskip()`.
- Integration tests requiring real credentials should be marked `@pytest.mark.integration`.

## Extending KnowledgeMall

`KnowledgeMall` is a `Mapping[str, KnowledgeFiles]`. To add declarative config-based construction, add a `@classmethod` factory. Keep the constructor signature simple: `KnowledgeMall(dict_or_kwargs)`.

## MCP server

The MCP server is a thin dispatch layer. When adding a new platform:
1. Add an `elif` branch to `_get_store()` in `mcp_server.py`
2. The tool functions themselves don't change — they delegate to `_get_store()`
