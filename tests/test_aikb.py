"""Tests for aikb — focused on the MutableMapping contract via LocalFilesProvider."""

import pytest

from aikb import (
    KnowledgeFiles,
    KnowledgeBaseProvider,
    LocalFilesProvider,
    LocalFiles,
    KnowledgeMall,
)


# ---------------------------------------------------------------------------
# LocalFiles — full MutableMapping contract
# ---------------------------------------------------------------------------


class TestLocalFiles:
    @pytest.fixture()
    def store(self, tmp_path):
        return LocalFiles(str(tmp_path))

    def test_setitem_getitem(self, store):
        store['notes.md'] = '# Notes\nSome content'
        assert store['notes.md'] == '# Notes\nSome content'

    def test_overwrite(self, store):
        store['a.md'] = 'v1'
        store['a.md'] = 'v2'
        assert store['a.md'] == 'v2'

    def test_delitem(self, store):
        store['tmp.md'] = 'delete me'
        del store['tmp.md']
        assert 'tmp.md' not in store

    def test_delitem_missing_raises(self, store):
        with pytest.raises(KeyError):
            del store['nonexistent.md']

    def test_getitem_missing_raises(self, store):
        with pytest.raises(KeyError):
            store['nonexistent.md']

    def test_iter(self, store):
        store['b.md'] = 'B'
        store['a.md'] = 'A'
        assert sorted(store) == ['a.md', 'b.md']

    def test_len(self, store):
        assert len(store) == 0
        store['a.md'] = 'A'
        assert len(store) == 1
        store['b.md'] = 'B'
        assert len(store) == 2

    def test_contains(self, store):
        store['x.md'] = 'X'
        assert 'x.md' in store
        assert 'y.md' not in store

    def test_contains_non_string(self, store):
        assert 42 not in store

    def test_keys_values_items(self, store):
        store['a.md'] = 'A'
        store['b.md'] = 'B'
        assert sorted(store.keys()) == ['a.md', 'b.md']
        assert sorted(store.values()) == ['A', 'B']
        assert sorted(store.items()) == [('a.md', 'A'), ('b.md', 'B')]

    def test_update(self, store):
        store.update({'one.md': '1', 'two.md': '2'})
        assert store['one.md'] == '1'
        assert store['two.md'] == '2'

    def test_repr(self, store):
        r = repr(store)
        assert 'KnowledgeFiles' in r
        assert 'LocalFilesProvider' in r


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
    def test_local_files_returns_knowledge_files(self, tmp_path):
        store = LocalFiles(str(tmp_path))
        assert isinstance(store, KnowledgeFiles)

    def test_local_files_custom_project_id(self, tmp_path):
        store = LocalFiles(str(tmp_path), project_id='myproj')
        assert store._project_id == 'myproj'


# ---------------------------------------------------------------------------
# KnowledgeMall
# ---------------------------------------------------------------------------


class TestKnowledgeMall:
    def test_access_by_name(self, tmp_path):
        s = LocalFiles(str(tmp_path))
        mall = KnowledgeMall(staging=s)
        assert mall['staging'] is s

    def test_iter(self, tmp_path):
        s1 = LocalFiles(str(tmp_path / 'a'))
        s2 = LocalFiles(str(tmp_path / 'b'))
        mall = KnowledgeMall(alpha=s1, beta=s2)
        assert sorted(mall) == ['alpha', 'beta']

    def test_len(self, tmp_path):
        s = LocalFiles(str(tmp_path))
        mall = KnowledgeMall(one=s)
        assert len(mall) == 1

    def test_missing_key_raises(self, tmp_path):
        mall = KnowledgeMall()
        with pytest.raises(KeyError):
            mall['nope']

    def test_repr(self, tmp_path):
        s = LocalFiles(str(tmp_path))
        mall = KnowledgeMall(staging=s)
        assert 'KnowledgeMall' in repr(mall)

    def test_dict_constructor(self, tmp_path):
        s = LocalFiles(str(tmp_path))
        mall = KnowledgeMall({'staging': s})
        assert mall['staging'] is s


# ---------------------------------------------------------------------------
# ClaudeProjectsProvider — import guard
# ---------------------------------------------------------------------------


class TestClaudeProjectsImportError:
    def test_informative_error_without_claudesync(self):
        """Verify that using ClaudeProjectsProvider without claudesync installed
        gives a helpful error message."""
        try:
            import claudesync  # noqa: F401

            pytest.skip('claudesync is installed')
        except ImportError:
            pass

        from aikb import ClaudeProjectsProvider

        provider = ClaudeProjectsProvider(session_key='fake')
        with pytest.raises(ImportError, match='pip install aikb'):
            provider._client
