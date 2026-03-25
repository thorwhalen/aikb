"""Core module: protocols, stores, providers, and factory functions for aikb."""

from collections.abc import Iterator, Mapping, MutableMapping
from functools import cached_property
from pathlib import Path
from typing import Protocol, runtime_checkable
import os


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class KnowledgeBaseProvider(Protocol):
    """Structural interface for knowledge base backends.

    Any object implementing these four methods can be used as a provider.
    """

    def list_files(self, project_id: str) -> Iterator[str]: ...

    def read_file(self, project_id: str, filename: str) -> str: ...

    def upsert_file(self, project_id: str, filename: str, content: str) -> None: ...

    def delete_file(self, project_id: str, filename: str) -> None: ...


# ---------------------------------------------------------------------------
# KnowledgeFiles — MutableMapping facade
# ---------------------------------------------------------------------------


class KnowledgeFiles(MutableMapping):
    """Dict-like access to knowledge files in an AI project.

    Keys are filenames (str), values are file contents (str).

    >>> import tempfile, os
    >>> store = LocalFiles(tempfile.mkdtemp())
    >>> store['notes.md'] = '# Notes'
    >>> store['notes.md']
    '# Notes'
    >>> list(store)
    ['notes.md']
    >>> len(store)
    1
    >>> del store['notes.md']
    >>> list(store)
    []
    """

    def __init__(self, provider: KnowledgeBaseProvider, *, project_id: str):
        self._provider = provider
        self._project_id = project_id

    def __getitem__(self, filename: str) -> str:
        return self._provider.read_file(self._project_id, filename)

    def __setitem__(self, filename: str, content: str) -> None:
        self._provider.upsert_file(self._project_id, filename, content)

    def __delitem__(self, filename: str) -> None:
        self._provider.delete_file(self._project_id, filename)

    def __iter__(self) -> Iterator[str]:
        yield from self._provider.list_files(self._project_id)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, filename: object) -> bool:
        if not isinstance(filename, str):
            return False
        return any(f == filename for f in self)

    def __repr__(self) -> str:
        provider_name = type(self._provider).__name__
        return (
            f"{type(self).__name__}({provider_name}, project_id={self._project_id!r})"
        )


# ---------------------------------------------------------------------------
# LocalFilesProvider
# ---------------------------------------------------------------------------


class LocalFilesProvider:
    """Local filesystem provider for knowledge files.

    Each ``project_id`` maps to a subdirectory under *rootdir*.
    Files are stored as UTF-8 text.
    """

    def __init__(self, rootdir: str, *, create_dirs: bool = True):
        self._rootdir = Path(rootdir)
        self._create_dirs = create_dirs

    def _project_dir(self, project_id: str) -> Path:
        d = self._rootdir / project_id
        if self._create_dirs:
            d.mkdir(parents=True, exist_ok=True)
        return d

    def list_files(self, project_id: str) -> Iterator[str]:
        d = self._project_dir(project_id)
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file():
                    yield p.name

    def read_file(self, project_id: str, filename: str) -> str:
        path = self._project_dir(project_id) / filename
        if not path.is_file():
            raise KeyError(filename)
        return path.read_text(encoding="utf-8")

    def upsert_file(self, project_id: str, filename: str, content: str) -> None:
        path = self._project_dir(project_id) / filename
        path.write_text(content, encoding="utf-8")

    def delete_file(self, project_id: str, filename: str) -> None:
        path = self._project_dir(project_id) / filename
        if not path.is_file():
            raise KeyError(filename)
        path.unlink()


# ---------------------------------------------------------------------------
# ClaudeProjectsProvider
# ---------------------------------------------------------------------------


def _check_dependency(module_name: str, *, install_hint: str):
    """Import *module_name* or raise an informative ``ImportError``."""
    try:
        return __import__(module_name)
    except ImportError:
        raise ImportError(
            f"{module_name!r} is required but not installed. {install_hint}"
        ) from None


class ClaudeProjectsProvider:
    """Claude Projects provider wrapping ClaudeSync.

    Requires ``pip install aikb[claude]``.

    Authentication priority:
    1. Explicit *session_key* parameter
    2. ``CLAUDE_SESSION_KEY`` environment variable
    3. ClaudeSync's own stored config
    """

    def __init__(
        self,
        session_key: str | None = None,
        *,
        organization_id: str | None = None,
    ):
        self._session_key = session_key or os.environ.get("CLAUDE_SESSION_KEY")
        self._organization_id = organization_id

    @cached_property
    def _client(self):
        _check_dependency(
            "claudesync",
            install_hint="Install with: pip install aikb[claude]",
        )
        from claudesync.providers.claude_ai import ClaudeAIProvider

        provider = ClaudeAIProvider(session_key=self._session_key)
        if self._organization_id:
            provider.organization_id = self._organization_id
        return provider

    def list_files(self, project_id: str) -> Iterator[str]:
        files = self._client.get_project_files(
            self._organization_id or self._client.organization_id, project_id
        )
        for f in files:
            yield f["file_name"]

    def read_file(self, project_id: str, filename: str) -> str:
        org_id = self._organization_id or self._client.organization_id
        files = self._client.get_project_files(org_id, project_id)
        for f in files:
            if f["file_name"] == filename:
                return f["content"]
        raise KeyError(filename)

    def upsert_file(self, project_id: str, filename: str, content: str) -> None:
        org_id = self._organization_id or self._client.organization_id
        self._client.upload_file(org_id, project_id, filename, content)

    def delete_file(self, project_id: str, filename: str) -> None:
        org_id = self._organization_id or self._client.organization_id
        files = self._client.get_project_files(org_id, project_id)
        for f in files:
            if f["file_name"] == filename:
                self._client.delete_file(org_id, project_id, f["uuid"])
                return
        raise KeyError(filename)


# ---------------------------------------------------------------------------
# KnowledgeMall — store of stores
# ---------------------------------------------------------------------------


class KnowledgeMall(Mapping):
    """A read-only mapping of names to :class:`KnowledgeFiles` stores.

    Useful for multi-project or multi-platform workflows.

    >>> import tempfile
    >>> mall = KnowledgeMall(staging=LocalFiles(tempfile.mkdtemp()))
    >>> list(mall)
    ['staging']
    >>> isinstance(mall['staging'], KnowledgeFiles)
    True
    """

    def __init__(self, stores: dict | None = None, /, **named_stores):
        self._stores: dict[str, KnowledgeFiles] = {
            **(stores or {}),
            **named_stores,
        }

    def __getitem__(self, name: str) -> KnowledgeFiles:
        try:
            return self._stores[name]
        except KeyError:
            raise KeyError(
                f"No store named {name!r}. Available: {list(self._stores)}"
            ) from None

    def __iter__(self) -> Iterator[str]:
        yield from self._stores

    def __len__(self) -> int:
        return len(self._stores)

    def __repr__(self) -> str:
        names = list(self._stores)
        return f"{type(self).__name__}({names})"


# ---------------------------------------------------------------------------
# Factory functions — progressive-disclosure entry points
# ---------------------------------------------------------------------------


def LocalFiles(rootdir: str, *, project_id: str = "default") -> KnowledgeFiles:
    """Create a local filesystem knowledge store.

    >>> import tempfile
    >>> store = LocalFiles(tempfile.mkdtemp())
    >>> store['ideas.md'] = '# Ideas\\nFirst idea'
    >>> store['ideas.md']
    '# Ideas\\nFirst idea'
    """
    return KnowledgeFiles(LocalFilesProvider(rootdir), project_id=project_id)


def ClaudeProject(
    project_id: str,
    *,
    session_key: str | None = None,
    organization_id: str | None = None,
) -> KnowledgeFiles:
    """Create a Claude Project knowledge store.

    Requires ``pip install aikb[claude]``.
    """
    provider = ClaudeProjectsProvider(
        session_key=session_key,
        organization_id=organization_id,
    )
    return KnowledgeFiles(provider, project_id=project_id)
