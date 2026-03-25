"""Core module: protocols, stores, providers, and factory functions for aikb."""

import datetime
import os
from collections.abc import Iterator, Mapping, MutableMapping
from functools import cached_property
from pathlib import Path
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_dependency(module_name: str, *, install_hint: str):
    """Import *module_name* or raise an informative ``ImportError``."""
    try:
        return __import__(module_name)
    except ImportError:
        raise ImportError(
            f"{module_name!r} is required but not installed. {install_hint}"
        ) from None


def _resolve_claude_session_key(session_key: str | None = None) -> str:
    """Resolve a Claude session key from multiple sources.

    Priority:
    1. Explicit *session_key* parameter
    2. ``CLAUDE_SESSION_KEY`` environment variable
    3. ClaudeSync stored config (``~/.claudesync/``)
    4. ``browser_cookie3`` (optional) — extract from browser cookies
    5. Raise ``RuntimeError`` with instructions
    """
    # 1. Explicit parameter
    if session_key:
        return session_key

    # 2. Environment variable
    env_key = os.environ.get("CLAUDE_SESSION_KEY")
    if env_key:
        return env_key

    # 3. ClaudeSync stored config
    try:
        from claudesync.configmanager import FileConfigManager, InMemoryConfigManager

        config = InMemoryConfigManager()
        config.load_from_file_config(FileConfigManager())
        stored_key, _expiry = config.get_session_key("claude.ai")
        if stored_key:
            return stored_key
    except Exception:
        pass  # claudesync not installed or config missing

    # 4. browser_cookie3 (optional)
    try:
        import browser_cookie3

        for browser_fn in (browser_cookie3.chrome, browser_cookie3.firefox):
            try:
                cj = browser_fn(domain_name="claude.ai")
                for cookie in cj:
                    if cookie.name == "sessionKey" and cookie.value:
                        return cookie.value
            except Exception:
                continue
    except ImportError:
        pass  # browser_cookie3 not installed

    # 5. Nothing found — raise with instructions
    raise RuntimeError(
        "Could not find a valid Claude session key. Tried:\n"
        "  1. Explicit session_key parameter\n"
        "  2. CLAUDE_SESSION_KEY environment variable\n"
        "  3. ClaudeSync stored config (~/.claudesync/)\n"
        "  4. Browser cookies (requires: pip install aikb[cookies])\n"
        "\n"
        "To obtain your session key:\n"
        "  1. Open https://claude.ai in your browser and log in\n"
        "  2. Open Developer Tools (F12) → Application → Cookies\n"
        "  3. Copy the value of the 'sessionKey' cookie (starts with 'sk-ant-')\n"
        "  4. Then either:\n"
        "     a. export CLAUDE_SESSION_KEY='sk-ant-...'\n"
        "     b. Pass session_key='sk-ant-...' to ClaudeProject() or ClaudeProjects()\n"
        "     c. Run 'pip install claudesync && claudesync auth login'\n"
    )


def _make_claude_config(session_key: str):
    """Create a ClaudeSync ``InMemoryConfigManager`` with the given session key."""
    from claudesync.configmanager import InMemoryConfigManager

    config = InMemoryConfigManager()
    # Use naive datetime — InMemoryConfigManager.get_session_key compares
    # with datetime.now() (naive), not datetime.now(utc).
    expiry = datetime.datetime.now() + datetime.timedelta(days=30)
    config.set_session_key("claude.ai", session_key, expiry)
    return config


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
    >>> store = LocalKb(tempfile.mkdtemp())
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


class ClaudeProjectsProvider:
    """Claude Projects provider wrapping ClaudeSync.

    Requires ``pip install aikb[claude]``.

    Session key resolution priority:
    1. Explicit *session_key* parameter
    2. ``CLAUDE_SESSION_KEY`` environment variable
    3. ClaudeSync stored config (``~/.claudesync/``)
    4. Browser cookies (requires ``pip install aikb[cookies]``)
    """

    def __init__(
        self,
        session_key: str | None = None,
        *,
        organization_id: str | None = None,
    ):
        self._session_key = session_key
        self._organization_id = organization_id

    @cached_property
    def _client(self):
        _check_dependency(
            "claudesync",
            install_hint="Install with: pip install aikb[claude]",
        )
        from claudesync.providers.claude_ai import ClaudeAIProvider

        session_key = _resolve_claude_session_key(self._session_key)
        config = _make_claude_config(session_key)
        return ClaudeAIProvider(config=config)

    @cached_property
    def _org_id(self) -> str:
        """Auto-resolve organization ID."""
        if self._organization_id:
            return self._organization_id
        orgs = self._client.get_organizations()
        if not orgs:
            raise RuntimeError("No organizations found for this session key.")
        if len(orgs) == 1:
            return orgs[0]["id"]
        names = [f"  - {o['name']} ({o['id']})" for o in orgs]
        raise RuntimeError(
            "Multiple organizations found. Pass organization_id=...:\n"
            + "\n".join(names)
        )

    def list_files(self, project_id: str) -> Iterator[str]:
        files = self._client.list_files(self._org_id, project_id)
        for f in files:
            yield f["file_name"]

    def read_file(self, project_id: str, filename: str) -> str:
        files = self._client.list_files(self._org_id, project_id)
        for f in files:
            if f["file_name"] == filename:
                return f["content"]
        raise KeyError(filename)

    def upsert_file(self, project_id: str, filename: str, content: str) -> None:
        self._client.upload_file(self._org_id, project_id, filename, content)

    def delete_file(self, project_id: str, filename: str) -> None:
        files = self._client.list_files(self._org_id, project_id)
        for f in files:
            if f["file_name"] == filename:
                self._client.delete_file(self._org_id, project_id, f["uuid"])
                return
        raise KeyError(filename)


# ---------------------------------------------------------------------------
# ClaudeProjects — Mapping of project names → KnowledgeFiles
# ---------------------------------------------------------------------------


class ClaudeProjects(Mapping):
    """Read-only mapping of Claude project names to KnowledgeFiles stores.

    >>> p = ClaudeProjects(session_key='sk-ant-...')  # doctest: +SKIP
    >>> list(p)                                        # doctest: +SKIP
    ['My Project', 'Another Project']
    >>> files = p['My Project']                        # doctest: +SKIP
    >>> list(files)                                    # doctest: +SKIP
    ['context.md', 'notes.md']
    """

    def __init__(
        self,
        *,
        session_key: str | None = None,
        organization_id: str | None = None,
        include_archived: bool = False,
    ):
        self._session_key = session_key
        self._organization_id = organization_id
        self._include_archived = include_archived

    @cached_property
    def _provider(self) -> ClaudeProjectsProvider:
        return ClaudeProjectsProvider(
            self._session_key,
            organization_id=self._organization_id,
        )

    @cached_property
    def _projects(self) -> dict[str, str]:
        """Build {display_name: project_uuid}.

        Duplicate names are disambiguated with a UUID prefix suffix.
        """
        raw = self._provider._client.get_projects(
            self._provider._org_id, include_archived=self._include_archived
        )
        # Group by name to detect collisions
        seen: dict[str, list[dict]] = {}
        for p in raw:
            seen.setdefault(p["name"], []).append(p)

        result: dict[str, str] = {}
        for name, entries in seen.items():
            if len(entries) == 1:
                result[name] = entries[0]["id"]
            else:
                for entry in entries:
                    short_id = entry["id"][:8]
                    result[f"{name} ({short_id})"] = entry["id"]
        return result

    def __getitem__(self, name: str) -> KnowledgeFiles:
        if name not in self._projects:
            raise KeyError(
                f"No project named {name!r}. Available: {list(self._projects)}"
            )
        project_id = self._projects[name]
        return KnowledgeFiles(self._provider, project_id=project_id)

    def __iter__(self) -> Iterator[str]:
        yield from self._projects

    def __len__(self) -> int:
        return len(self._projects)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._projects)})"


# ---------------------------------------------------------------------------
# Factory functions — progressive-disclosure entry points
# ---------------------------------------------------------------------------


_DEFAULT_LOCAL_DIR = os.environ.get("AIKB_LOCAL_DIR") or str(
    Path.home() / ".local" / "share" / "aikb" / "localkb_files"
)


def LocalKb(
    rootdir: str | None = None,
    *,
    project_id: str = "default",
) -> KnowledgeFiles:
    """Create a local filesystem knowledge store.

    Files are stored in ``rootdir / project_id /``.
    Defaults to ``~/.local/share/aikb/localkb_files/`` or the
    ``AIKB_LOCAL_DIR`` environment variable.

    >>> import tempfile
    >>> store = LocalKb(tempfile.mkdtemp())
    >>> store['ideas.md'] = '# Ideas\\nFirst idea'
    >>> store['ideas.md']
    '# Ideas\\nFirst idea'
    """
    if rootdir is None:
        rootdir = os.environ.get("AIKB_LOCAL_DIR") or str(
            Path.home() / ".local" / "share" / "aikb" / "localkb_files"
        )
    return KnowledgeFiles(LocalFilesProvider(rootdir), project_id=project_id)


def ClaudeProject(
    project_id: str,
    *,
    session_key: str | None = None,
    organization_id: str | None = None,
) -> KnowledgeFiles:
    """Create a Claude Project knowledge store.

    Requires ``pip install aikb[claude]``.

    Session key is resolved automatically (env var, ClaudeSync config,
    browser cookies). Pass *session_key* explicitly to override.
    """
    provider = ClaudeProjectsProvider(
        session_key=session_key,
        organization_id=organization_id,
    )
    return KnowledgeFiles(provider, project_id=project_id)
