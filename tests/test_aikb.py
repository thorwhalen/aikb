"""Tests for aikb — focused on the MutableMapping contract via LocalFilesProvider."""

import pytest

from aikb import (
    KnowledgeFiles,
    KnowledgeBaseProvider,
    LocalFilesProvider,
    LocalKb,
)
from aikb.base import _resolve_claude_session_key


# ---------------------------------------------------------------------------
# LocalKb — full MutableMapping contract
# ---------------------------------------------------------------------------


class TestLocalKb:
    @pytest.fixture()
    def store(self, tmp_path):
        return LocalKb(str(tmp_path))

    def test_setitem_getitem(self, store):
        store["notes.md"] = "# Notes\nSome content"
        assert store["notes.md"] == "# Notes\nSome content"

    def test_overwrite(self, store):
        store["a.md"] = "v1"
        store["a.md"] = "v2"
        assert store["a.md"] == "v2"

    def test_delitem(self, store):
        store["tmp.md"] = "delete me"
        del store["tmp.md"]
        assert "tmp.md" not in store

    def test_delitem_missing_raises(self, store):
        with pytest.raises(KeyError):
            del store["nonexistent.md"]

    def test_getitem_missing_raises(self, store):
        with pytest.raises(KeyError):
            store["nonexistent.md"]

    def test_iter(self, store):
        store["b.md"] = "B"
        store["a.md"] = "A"
        assert sorted(store) == ["a.md", "b.md"]

    def test_len(self, store):
        assert len(store) == 0
        store["a.md"] = "A"
        assert len(store) == 1
        store["b.md"] = "B"
        assert len(store) == 2

    def test_contains(self, store):
        store["x.md"] = "X"
        assert "x.md" in store
        assert "y.md" not in store

    def test_contains_non_string(self, store):
        assert 42 not in store

    def test_keys_values_items(self, store):
        store["a.md"] = "A"
        store["b.md"] = "B"
        assert sorted(store.keys()) == ["a.md", "b.md"]
        assert sorted(store.values()) == ["A", "B"]
        assert sorted(store.items()) == [("a.md", "A"), ("b.md", "B")]

    def test_update(self, store):
        store.update({"one.md": "1", "two.md": "2"})
        assert store["one.md"] == "1"
        assert store["two.md"] == "2"

    def test_repr(self, store):
        r = repr(store)
        assert "KnowledgeFiles" in r
        assert "LocalFilesProvider" in r


# ---------------------------------------------------------------------------
# LocalKb defaults
# ---------------------------------------------------------------------------


class TestLocalKbDefaults:
    def test_default_dir(self, tmp_path, monkeypatch):
        """LocalKb() with no args uses AIKB_LOCAL_DIR or ~/.local/share/aikb/..."""
        monkeypatch.setenv("AIKB_LOCAL_DIR", str(tmp_path))
        store = LocalKb()
        store["test.md"] = "hello"
        assert store["test.md"] == "hello"
        # File should be under tmp_path/default/
        assert (tmp_path / "default" / "test.md").read_text() == "hello"

    def test_env_var_override(self, tmp_path, monkeypatch):
        """AIKB_LOCAL_DIR overrides the default directory."""
        custom_dir = tmp_path / "custom"
        monkeypatch.setenv("AIKB_LOCAL_DIR", str(custom_dir))
        store = LocalKb()
        store["x.md"] = "X"
        assert (custom_dir / "default" / "x.md").read_text() == "X"

    def test_explicit_rootdir_takes_precedence(self, tmp_path, monkeypatch):
        """Explicit rootdir overrides AIKB_LOCAL_DIR."""
        monkeypatch.setenv("AIKB_LOCAL_DIR", str(tmp_path / "env"))
        explicit = tmp_path / "explicit"
        store = LocalKb(str(explicit))
        store["y.md"] = "Y"
        assert (explicit / "default" / "y.md").read_text() == "Y"
        assert not (tmp_path / "env" / "default" / "y.md").exists()


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_local_provider_satisfies_protocol(self, tmp_path):
        provider = LocalFilesProvider(str(tmp_path))
        assert isinstance(provider, KnowledgeBaseProvider)


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


class TestFactoryFunctions:
    def test_local_kb_returns_knowledge_files(self, tmp_path):
        store = LocalKb(str(tmp_path))
        assert isinstance(store, KnowledgeFiles)

    def test_local_kb_custom_project_id(self, tmp_path):
        store = LocalKb(str(tmp_path), project_id="myproj")
        assert store._project_id == "myproj"


# ---------------------------------------------------------------------------
# Session key resolution
# ---------------------------------------------------------------------------


class TestResolveClaudeSessionKey:
    def test_explicit_key_returned(self):
        assert _resolve_claude_session_key("sk-ant-test") == "sk-ant-test"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_KEY", "sk-ant-env")
        assert _resolve_claude_session_key() == "sk-ant-env"

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_KEY", "sk-ant-env")
        assert _resolve_claude_session_key("sk-ant-explicit") == "sk-ant-explicit"

    def test_raises_when_nothing_found(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_SESSION_KEY", raising=False)
        with pytest.raises(RuntimeError, match="Could not find a valid Claude session key"):
            _resolve_claude_session_key()


# ---------------------------------------------------------------------------
# ClaudeProjectsProvider — import guard
# ---------------------------------------------------------------------------


class TestClaudeProjectsImportError:
    def test_informative_error_without_claudesync(self):
        """Verify that using ClaudeProjectsProvider without claudesync installed
        gives a helpful error message."""
        try:
            import claudesync  # noqa: F401

            pytest.skip("claudesync is installed")
        except ImportError:
            pass

        from aikb import ClaudeProjectsProvider

        provider = ClaudeProjectsProvider(session_key="fake")
        with pytest.raises(ImportError, match="pip install aikb"):
            provider._client
