"""Tests for aikb.sync — bidirectional sync engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aikb.sync import (
    ActionType,
    ConflictPolicy,
    SyncAction,
    SyncConflictError,
    clone,
    content_hash,
    load_manifest,
    propagate,
    pull,
    push,
    reconcile,
    resolve_conflicts,
    save_manifest,
    snapshot,
    status,
    sync,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

H = content_hash  # shorthand


# ---------------------------------------------------------------------------
# content_hash / snapshot
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_content(self):
        assert content_hash("a") != content_hash("b")

    def test_sha256_length(self):
        assert len(content_hash("x")) == 64  # SHA-256 hex digest


class TestSnapshot:
    def test_empty_store(self):
        assert snapshot({}) == {}

    def test_basic(self):
        store = {"a.md": "alpha", "b.md": "beta"}
        snap = snapshot(store)
        assert set(snap) == {"a.md", "b.md"}
        assert snap["a.md"] == H("alpha")

    def test_custom_hash(self):
        snap = snapshot({"x": "val"}, hash_fn=lambda c: f"custom-{c}")
        assert snap["x"] == "custom-val"


# ---------------------------------------------------------------------------
# Three-way reconciliation (7 cases)
# ---------------------------------------------------------------------------


class TestReconcileThreeWay:
    """All seven cases from the Unison algorithm."""

    def test_case1a_no_changes(self):
        m = {"f": H("v")}
        actions = reconcile({"f": H("v")}, {"f": H("v")}, manifest=m)
        assert len(actions) == 1
        assert actions[0].action is ActionType.NOOP

    def test_case1b_a_modified(self):
        m = {"f": H("old")}
        actions = reconcile({"f": H("new")}, {"f": H("old")}, manifest=m)
        assert actions[0].action is ActionType.UPDATE
        assert actions[0].direction == 'a_to_b'

    def test_case1c_b_modified(self):
        m = {"f": H("old")}
        actions = reconcile({"f": H("old")}, {"f": H("new")}, manifest=m)
        assert actions[0].action is ActionType.UPDATE
        assert actions[0].direction == 'b_to_a'

    def test_case1d_both_modified_different(self):
        m = {"f": H("old")}
        actions = reconcile({"f": H("new_a")}, {"f": H("new_b")}, manifest=m)
        assert actions[0].action is ActionType.CONFLICT

    def test_case1d_both_modified_same(self):
        """Same change on both sides is NOT a conflict."""
        m = {"f": H("old")}
        actions = reconcile({"f": H("same")}, {"f": H("same")}, manifest=m)
        assert actions[0].action is ActionType.NOOP

    def test_case2_b_deleted(self):
        m = {"f": H("v")}
        actions = reconcile({"f": H("v")}, {}, manifest=m)
        assert actions[0].action is ActionType.DELETE
        assert actions[0].direction == 'b_to_a'

    def test_case2_a_modified_b_deleted_conflict(self):
        m = {"f": H("old")}
        actions = reconcile({"f": H("new")}, {}, manifest=m)
        assert actions[0].action is ActionType.CONFLICT

    def test_case3_a_deleted(self):
        m = {"f": H("v")}
        actions = reconcile({}, {"f": H("v")}, manifest=m)
        assert actions[0].action is ActionType.DELETE
        assert actions[0].direction == 'a_to_b'

    def test_case3_b_modified_a_deleted_conflict(self):
        m = {"f": H("old")}
        actions = reconcile({}, {"f": H("new")}, manifest=m)
        assert actions[0].action is ActionType.CONFLICT

    def test_case4_both_deleted(self):
        m = {"f": H("v")}
        actions = reconcile({}, {}, manifest=m)
        assert actions[0].action is ActionType.NOOP

    def test_case5_both_created_same(self):
        actions = reconcile({"f": H("v")}, {"f": H("v")}, manifest={})
        assert actions[0].action is ActionType.NOOP

    def test_case5_both_created_different(self):
        actions = reconcile({"f": H("a")}, {"f": H("b")}, manifest={})
        assert actions[0].action is ActionType.CONFLICT

    def test_case6_created_in_a(self):
        actions = reconcile({"f": H("v")}, {}, manifest={})
        assert actions[0].action is ActionType.CREATE
        assert actions[0].direction == 'a_to_b'

    def test_case7_created_in_b(self):
        actions = reconcile({}, {"f": H("v")}, manifest={})
        assert actions[0].action is ActionType.CREATE
        assert actions[0].direction == 'b_to_a'


# ---------------------------------------------------------------------------
# Two-way reconciliation (no manifest)
# ---------------------------------------------------------------------------


class TestReconcileTwoWay:
    def test_identical(self):
        snap = {"f": H("v")}
        actions = reconcile(snap, snap)
        assert actions[0].action is ActionType.NOOP

    def test_a_only(self):
        actions = reconcile({"f": H("v")}, {})
        assert actions[0].action is ActionType.CREATE
        assert actions[0].direction == 'a_to_b'

    def test_b_only(self):
        actions = reconcile({}, {"f": H("v")})
        assert actions[0].action is ActionType.CREATE
        assert actions[0].direction == 'b_to_a'

    def test_different_is_conflict(self):
        actions = reconcile({"f": H("a")}, {"f": H("b")})
        assert actions[0].action is ActionType.CONFLICT


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    @pytest.fixture
    def conflicting_actions(self):
        return [
            SyncAction("ok.md", ActionType.UPDATE, 'a_to_b', 'modified'),
            SyncAction("conflict.md", ActionType.CONFLICT, 'both', 'both modified',
                        a_hash="ha", b_hash="hb", manifest_hash="hm"),
        ]

    def test_raise_policy(self, conflicting_actions):
        with pytest.raises(SyncConflictError) as exc_info:
            resolve_conflicts(conflicting_actions, on_conflict=ConflictPolicy.RAISE)
        assert len(exc_info.value.conflicts) == 1

    def test_skip_policy(self, conflicting_actions):
        resolved = resolve_conflicts(conflicting_actions, on_conflict=ConflictPolicy.SKIP)
        assert len(resolved) == 1
        assert resolved[0].filename == "ok.md"

    def test_a_wins_policy(self, conflicting_actions):
        resolved = resolve_conflicts(conflicting_actions, on_conflict=ConflictPolicy.A_WINS)
        assert len(resolved) == 2
        conflict_resolved = [a for a in resolved if a.filename == "conflict.md"][0]
        assert conflict_resolved.action is ActionType.UPDATE
        assert conflict_resolved.direction == 'a_to_b'

    def test_b_wins_policy(self, conflicting_actions):
        resolved = resolve_conflicts(conflicting_actions, on_conflict=ConflictPolicy.B_WINS)
        conflict_resolved = [a for a in resolved if a.filename == "conflict.md"][0]
        assert conflict_resolved.action is ActionType.UPDATE
        assert conflict_resolved.direction == 'b_to_a'

    def test_custom_callable(self, conflicting_actions):
        def my_resolver(action: SyncAction) -> SyncAction:
            return SyncAction(action.filename, ActionType.NOOP, 'none', 'skipped by custom')

        resolved = resolve_conflicts(conflicting_actions, on_conflict=my_resolver)
        conflict_resolved = [a for a in resolved if a.filename == "conflict.md"][0]
        assert conflict_resolved.action is ActionType.NOOP

    def test_no_conflicts_passes_through(self):
        actions = [SyncAction("f", ActionType.UPDATE, 'a_to_b', 'ok')]
        assert resolve_conflicts(actions) == actions


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------


class TestPropagate:
    def test_create_a_to_b(self):
        a = {"f.md": "content"}
        b = {}
        actions = [SyncAction("f.md", ActionType.CREATE, 'a_to_b', 'new')]
        applied = propagate(actions, a, b)
        assert b["f.md"] == "content"
        assert len(applied) == 1

    def test_create_b_to_a(self):
        a = {}
        b = {"f.md": "content"}
        actions = [SyncAction("f.md", ActionType.CREATE, 'b_to_a', 'new')]
        propagate(actions, a, b)
        assert a["f.md"] == "content"

    def test_update_a_to_b(self):
        a = {"f.md": "new"}
        b = {"f.md": "old"}
        actions = [SyncAction("f.md", ActionType.UPDATE, 'a_to_b', 'changed')]
        propagate(actions, a, b)
        assert b["f.md"] == "new"

    def test_delete_a_to_b(self):
        a = {}
        b = {"f.md": "bye"}
        actions = [SyncAction("f.md", ActionType.DELETE, 'a_to_b', 'removed')]
        propagate(actions, a, b)
        assert "f.md" not in b

    def test_delete_b_to_a(self):
        a = {"f.md": "bye"}
        b = {}
        actions = [SyncAction("f.md", ActionType.DELETE, 'b_to_a', 'removed')]
        propagate(actions, a, b)
        assert "f.md" not in a

    def test_dry_run_no_changes(self):
        a = {"f.md": "content"}
        b = {}
        actions = [SyncAction("f.md", ActionType.CREATE, 'a_to_b', 'new')]
        applied = propagate(actions, a, b, dry_run=True)
        assert len(applied) == 1
        assert b == {}  # unchanged

    def test_skips_conflicts_and_noops(self):
        a = {"f.md": "v"}
        b = {}
        actions = [
            SyncAction("noop.md", ActionType.NOOP, 'none', 'same'),
            SyncAction("conflict.md", ActionType.CONFLICT, 'both', 'conflict'),
            SyncAction("f.md", ActionType.CREATE, 'a_to_b', 'new'),
        ]
        applied = propagate(actions, a, b)
        assert len(applied) == 1
        assert applied[0].filename == "f.md"


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


class TestManifest:
    def test_load_missing_returns_empty(self, tmp_path):
        assert load_manifest(tmp_path / "nonexistent.json") == {}

    def test_save_load_roundtrip(self, tmp_path):
        path = tmp_path / "manifest.json"
        data = {"a.md": "hash_a", "b.md": "hash_b"}
        save_manifest(data, path=path)
        loaded = load_manifest(path)
        assert loaded == data

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "manifest.json"
        save_manifest({"f": "h"}, path=path)
        assert path.is_file()

    def test_save_includes_meta(self, tmp_path):
        path = tmp_path / "m.json"
        save_manifest({"f": "h"}, path=path)
        raw = json.loads(path.read_text())
        assert "_meta" in raw
        assert "synced_at" in raw["_meta"]


# ---------------------------------------------------------------------------
# High-level: push
# ---------------------------------------------------------------------------


class TestPush:
    def test_push_new_files(self):
        src = {"a.md": "alpha", "b.md": "beta"}
        tgt = {}
        push(src, tgt)
        assert tgt == src

    def test_push_updates(self):
        src = {"f.md": "new"}
        tgt = {"f.md": "old"}
        push(src, tgt)
        assert tgt["f.md"] == "new"

    def test_push_with_delete(self):
        src = {"a.md": "keep"}
        tgt = {"a.md": "keep", "extra.md": "bye"}
        push(src, tgt, delete=True)
        assert "extra.md" not in tgt

    def test_push_without_delete_keeps_extras(self):
        src = {"a.md": "v"}
        tgt = {"a.md": "v", "extra.md": "stays"}
        push(src, tgt, delete=False)
        assert "extra.md" in tgt

    def test_push_dry_run(self):
        src = {"a.md": "v"}
        tgt = {}
        actions = push(src, tgt, dry_run=True)
        assert len(actions) == 1
        assert tgt == {}

    def test_push_noop_when_identical(self):
        store = {"f.md": "same"}
        actions = push(dict(store), dict(store))
        assert len(actions) == 0  # no applied actions (all NOOP)


# ---------------------------------------------------------------------------
# High-level: pull
# ---------------------------------------------------------------------------


class TestPull:
    def test_pull_copies_from_source(self):
        src = {"f.md": "content"}
        tgt = {}
        pull(tgt, src)
        assert tgt["f.md"] == "content"


# ---------------------------------------------------------------------------
# High-level: clone
# ---------------------------------------------------------------------------


class TestClone:
    def test_clone_copies_all(self):
        src = {"a.md": "1", "b.md": "2"}
        tgt = {}
        clone(src, tgt)
        assert tgt == src

    def test_clone_clears_target(self):
        src = {"a.md": "new"}
        tgt = {"old.md": "gone"}
        clone(src, tgt)
        assert "old.md" not in tgt
        assert tgt == src

    def test_clone_creates_manifest(self, tmp_path):
        path = tmp_path / "m.json"
        src = {"f.md": "v"}
        clone(src, {}, manifest_path=path)
        m = load_manifest(path)
        assert "f.md" in m

    def test_clone_returns_actions(self):
        actions = clone({"a.md": "v"}, {})
        assert len(actions) == 1
        assert actions[0].action is ActionType.CREATE


# ---------------------------------------------------------------------------
# High-level: status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_read_only(self):
        a = {"f.md": "a_content"}
        b = {"f.md": "b_content"}
        a_copy, b_copy = dict(a), dict(b)
        status(a, b)
        assert a == a_copy
        assert b == b_copy

    def test_status_with_manifest(self):
        m = {"f.md": H("old")}
        actions = status({"f.md": "new"}, {"f.md": "old"}, manifest=m)
        updates = [a for a in actions if a.action is ActionType.UPDATE]
        assert len(updates) == 1


# ---------------------------------------------------------------------------
# High-level: sync
# ---------------------------------------------------------------------------


class TestSync:
    def test_sync_bidirectional(self, tmp_path):
        manifest_path = tmp_path / "m.json"
        a = {"shared.md": "v1"}
        b = {"shared.md": "v1"}
        # Create initial manifest
        save_manifest(snapshot(a), path=manifest_path)

        # A creates a file, B creates a different file
        a["from_a.md"] = "new_a"
        b["from_b.md"] = "new_b"

        sync(a, b, manifest_path=manifest_path)

        assert "from_a.md" in b
        assert "from_b.md" in a
        assert b["from_a.md"] == "new_a"
        assert a["from_b.md"] == "new_b"

    def test_sync_raises_on_conflict(self):
        m = {"f.md": H("old")}
        a = {"f.md": "new_a"}
        b = {"f.md": "new_b"}
        with pytest.raises(SyncConflictError):
            sync(a, b, manifest=m)

    def test_sync_with_conflict_policy(self):
        m = {"f.md": H("old")}
        a = {"f.md": "new_a"}
        b = {"f.md": "new_b"}
        sync(a, b, manifest=m, on_conflict=ConflictPolicy.A_WINS)
        assert b["f.md"] == "new_a"

    def test_sync_updates_manifest(self, tmp_path):
        manifest_path = tmp_path / "m.json"
        a = {"f.md": "v1"}
        b = {}
        sync(a, b, manifest_path=manifest_path)
        m = load_manifest(manifest_path)
        assert "f.md" in m

    def test_sync_empty_manifest_first_sync(self):
        """First sync with no prior manifest — all files look 'created'."""
        a = {"a.md": "from_a"}
        b = {"b.md": "from_b"}
        sync(a, b)  # no manifest → empty → everything is "created"
        assert "b.md" in a
        assert "a.md" in b


# ---------------------------------------------------------------------------
# Integration with LocalKb
# ---------------------------------------------------------------------------


class TestIntegrationLocalKb:
    def test_push_between_local_stores(self, tmp_path):
        from aikb import LocalKb

        src = LocalKb(str(tmp_path / "src"), project_id="p")
        tgt = LocalKb(str(tmp_path / "tgt"), project_id="p")

        src["readme.md"] = "# Hello"
        src["notes.md"] = "Some notes"

        push(src, tgt)

        assert tgt["readme.md"] == "# Hello"
        assert tgt["notes.md"] == "Some notes"

    def test_sync_local_stores(self, tmp_path):
        from aikb import LocalKb

        manifest_path = tmp_path / "manifest.json"
        a = LocalKb(str(tmp_path / "a"), project_id="p")
        b = LocalKb(str(tmp_path / "b"), project_id="p")

        # Initial state
        a["shared.md"] = "v1"
        clone(a, b, manifest_path=manifest_path)

        # Diverge
        a["from_a.md"] = "new in a"
        b["from_b.md"] = "new in b"

        sync(a, b, manifest_path=manifest_path)

        assert "from_a.md" in b
        assert "from_b.md" in a
