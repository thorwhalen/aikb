"""Bidirectional sync engine for MutableMapping stores.

Provides push/pull/clone/sync/status operations that work with any
``collections.abc.MutableMapping`` — plain dicts, aikb KnowledgeFiles,
dol stores, or anything else that implements the mapping protocol.

The sync engine is store-agnostic: it never imports aikb.base or any
provider. All it needs is ``__getitem__``, ``__setitem__``, ``__delitem__``,
and ``__iter__``.

Zero external dependencies — stdlib only (hashlib, json, dataclasses, enum).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Literal


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def content_hash(content: str, *, algorithm: str = 'sha256') -> str:
    """Return hex digest of *content*.

    >>> content_hash("hello")[:12]
    '2cf24dba5fb0'
    """
    return hashlib.new(algorithm, content.encode('utf-8')).hexdigest()


def snapshot(
    store: MutableMapping,
    *,
    hash_fn: Callable[[str], str] = content_hash,
) -> dict[str, str]:
    """Return ``{filename: content_hash}`` for every key in *store*."""
    return {k: hash_fn(store[k]) for k in store}


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ActionType(Enum):
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    CONFLICT = 'conflict'
    NOOP = 'noop'


@dataclass(frozen=True)
class SyncAction:
    """A single classified sync operation."""

    filename: str
    action: ActionType
    direction: Literal['a_to_b', 'b_to_a', 'both', 'none']
    reason: str
    a_hash: str | None = None
    b_hash: str | None = None
    manifest_hash: str | None = None


class ConflictPolicy(Enum):
    """Built-in conflict resolution strategies."""

    RAISE = 'raise'
    SKIP = 'skip'
    A_WINS = 'a_wins'
    B_WINS = 'b_wins'


class SyncConflictError(Exception):
    """Raised when unresolved conflicts exist and policy is RAISE."""

    def __init__(self, conflicts: list[SyncAction]):
        self.conflicts = conflicts
        filenames = [c.filename for c in conflicts]
        super().__init__(
            f"Sync conflicts on {len(conflicts)} file(s): {filenames}"
        )


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def load_manifest(path: str | Path) -> dict[str, str]:
    """Load a manifest from a JSON file.

    Returns an empty dict if the file does not exist.
    """
    p = Path(path)
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding='utf-8'))
    return data.get('files', data)  # support raw dict or structured format


def save_manifest(
    manifest: dict[str, str],
    *,
    path: str | Path,
) -> None:
    """Save a manifest to a JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        '_meta': {
            'synced_at': datetime.now(timezone.utc).isoformat(),
            'hash_algorithm': 'sha256',
        },
        'files': manifest,
    }
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding='utf-8')


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile(
    snap_a: dict[str, str],
    snap_b: dict[str, str],
    *,
    manifest: dict[str, str] | None = None,
) -> list[SyncAction]:
    """Three-way reconciliation between snapshots A, B and a manifest.

    If *manifest* is ``None``, falls back to two-way comparison (cannot
    distinguish "created on A" from "deleted on B").

    Returns a list of :class:`SyncAction` instances — one per filename
    across the union of all three sets.
    """
    if manifest is None:
        return _reconcile_two_way(snap_a, snap_b)
    return _reconcile_three_way(snap_a, snap_b, manifest)


def _reconcile_two_way(
    snap_a: dict[str, str],
    snap_b: dict[str, str],
) -> list[SyncAction]:
    actions: list[SyncAction] = []
    all_keys = set(snap_a) | set(snap_b)

    for k in sorted(all_keys):
        in_a = k in snap_a
        in_b = k in snap_b

        if in_a and in_b:
            if snap_a[k] == snap_b[k]:
                actions.append(SyncAction(k, ActionType.NOOP, 'none', 'identical'))
            else:
                actions.append(SyncAction(
                    k, ActionType.CONFLICT, 'both',
                    'different content, no manifest to disambiguate',
                    a_hash=snap_a[k], b_hash=snap_b[k],
                ))
        elif in_a:
            actions.append(SyncAction(
                k, ActionType.CREATE, 'a_to_b', 'exists only in A',
                a_hash=snap_a[k],
            ))
        else:
            actions.append(SyncAction(
                k, ActionType.CREATE, 'b_to_a', 'exists only in B',
                b_hash=snap_b[k],
            ))

    return actions


def _reconcile_three_way(
    snap_a: dict[str, str],
    snap_b: dict[str, str],
    manifest: dict[str, str],
) -> list[SyncAction]:
    actions: list[SyncAction] = []
    all_keys = set(snap_a) | set(snap_b) | set(manifest)

    for k in sorted(all_keys):
        in_a = k in snap_a
        in_b = k in snap_b
        in_m = k in manifest

        ha = snap_a.get(k)
        hb = snap_b.get(k)
        hm = manifest.get(k)

        if in_m and in_a and in_b:
            # Case 1: existed in all three
            if ha == hm and hb == hm:
                actions.append(SyncAction(k, ActionType.NOOP, 'none', 'unchanged'))
            elif ha != hm and hb == hm:
                actions.append(SyncAction(
                    k, ActionType.UPDATE, 'a_to_b', 'modified in A',
                    a_hash=ha, b_hash=hb, manifest_hash=hm,
                ))
            elif ha == hm and hb != hm:
                actions.append(SyncAction(
                    k, ActionType.UPDATE, 'b_to_a', 'modified in B',
                    a_hash=ha, b_hash=hb, manifest_hash=hm,
                ))
            else:
                # Both modified
                if ha == hb:
                    # Same change on both sides — no conflict
                    actions.append(SyncAction(
                        k, ActionType.NOOP, 'none',
                        'modified identically in both',
                        a_hash=ha, b_hash=hb, manifest_hash=hm,
                    ))
                else:
                    actions.append(SyncAction(
                        k, ActionType.CONFLICT, 'both',
                        'modified differently in both',
                        a_hash=ha, b_hash=hb, manifest_hash=hm,
                    ))
        elif in_m and in_a and not in_b:
            # Case 2: B deleted
            if ha == hm:
                actions.append(SyncAction(
                    k, ActionType.DELETE, 'b_to_a', 'deleted in B',
                    a_hash=ha, manifest_hash=hm,
                ))
            else:
                # A modified, B deleted — conflict
                actions.append(SyncAction(
                    k, ActionType.CONFLICT, 'both',
                    'modified in A, deleted in B',
                    a_hash=ha, manifest_hash=hm,
                ))
        elif in_m and not in_a and in_b:
            # Case 3: A deleted
            if hb == hm:
                actions.append(SyncAction(
                    k, ActionType.DELETE, 'a_to_b', 'deleted in A',
                    b_hash=hb, manifest_hash=hm,
                ))
            else:
                # B modified, A deleted — conflict
                actions.append(SyncAction(
                    k, ActionType.CONFLICT, 'both',
                    'deleted in A, modified in B',
                    b_hash=hb, manifest_hash=hm,
                ))
        elif in_m and not in_a and not in_b:
            # Case 4: both deleted
            actions.append(SyncAction(
                k, ActionType.NOOP, 'none', 'deleted in both',
                manifest_hash=hm,
            ))
        elif not in_m and in_a and in_b:
            # Case 5: both created
            if ha == hb:
                actions.append(SyncAction(
                    k, ActionType.NOOP, 'none', 'created identically in both',
                    a_hash=ha, b_hash=hb,
                ))
            else:
                actions.append(SyncAction(
                    k, ActionType.CONFLICT, 'both',
                    'created differently in both',
                    a_hash=ha, b_hash=hb,
                ))
        elif not in_m and in_a and not in_b:
            # Case 6: created in A
            actions.append(SyncAction(
                k, ActionType.CREATE, 'a_to_b', 'created in A',
                a_hash=ha,
            ))
        elif not in_m and not in_a and in_b:
            # Case 7: created in B
            actions.append(SyncAction(
                k, ActionType.CREATE, 'b_to_a', 'created in B',
                b_hash=hb,
            ))

    return actions


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


def resolve_conflicts(
    actions: list[SyncAction],
    *,
    on_conflict: ConflictPolicy | Callable[[SyncAction], SyncAction] = ConflictPolicy.RAISE,
) -> list[SyncAction]:
    """Apply a conflict resolution policy, returning a resolved action list.

    *on_conflict* can be a :class:`ConflictPolicy` enum or a callable that
    receives a conflict :class:`SyncAction` and returns a resolved one.
    """
    conflicts = [a for a in actions if a.action is ActionType.CONFLICT]

    if not conflicts:
        return actions

    if callable(on_conflict) and not isinstance(on_conflict, ConflictPolicy):
        resolved = {c.filename: on_conflict(c) for c in conflicts}
        return [resolved.get(a.filename, a) if a.action is ActionType.CONFLICT else a for a in actions]

    if on_conflict is ConflictPolicy.RAISE:
        raise SyncConflictError(conflicts)

    if on_conflict is ConflictPolicy.SKIP:
        return [a for a in actions if a.action is not ActionType.CONFLICT]

    if on_conflict is ConflictPolicy.A_WINS:
        return [_resolve_a_wins(a) if a.action is ActionType.CONFLICT else a for a in actions]

    if on_conflict is ConflictPolicy.B_WINS:
        return [_resolve_b_wins(a) if a.action is ActionType.CONFLICT else a for a in actions]

    raise ValueError(f"Unknown conflict policy: {on_conflict!r}")


def _resolve_a_wins(action: SyncAction) -> SyncAction:
    if action.a_hash is not None:
        return SyncAction(
            action.filename, ActionType.UPDATE, 'a_to_b',
            f'{action.reason} (resolved: A wins)',
            a_hash=action.a_hash, b_hash=action.b_hash,
            manifest_hash=action.manifest_hash,
        )
    # A deleted the file — propagate deletion to B
    return SyncAction(
        action.filename, ActionType.DELETE, 'a_to_b',
        f'{action.reason} (resolved: A wins)',
        b_hash=action.b_hash, manifest_hash=action.manifest_hash,
    )


def _resolve_b_wins(action: SyncAction) -> SyncAction:
    if action.b_hash is not None:
        return SyncAction(
            action.filename, ActionType.UPDATE, 'b_to_a',
            f'{action.reason} (resolved: B wins)',
            a_hash=action.a_hash, b_hash=action.b_hash,
            manifest_hash=action.manifest_hash,
        )
    # B deleted the file — propagate deletion to A
    return SyncAction(
        action.filename, ActionType.DELETE, 'b_to_a',
        f'{action.reason} (resolved: B wins)',
        a_hash=action.a_hash, manifest_hash=action.manifest_hash,
    )


# ---------------------------------------------------------------------------
# Propagation
# ---------------------------------------------------------------------------


def propagate(
    actions: list[SyncAction],
    a: MutableMapping,
    b: MutableMapping,
    *,
    dry_run: bool = False,
) -> list[SyncAction]:
    """Execute non-conflict, non-noop actions against stores *a* and *b*.

    Returns the list of actions that were actually applied.
    Skips CONFLICT and NOOP actions silently.
    """
    applied: list[SyncAction] = []

    for act in actions:
        if act.action in (ActionType.CONFLICT, ActionType.NOOP):
            continue

        if not dry_run:
            if act.direction == 'a_to_b':
                if act.action in (ActionType.CREATE, ActionType.UPDATE):
                    b[act.filename] = a[act.filename]
                elif act.action is ActionType.DELETE:
                    del b[act.filename]
            elif act.direction == 'b_to_a':
                if act.action in (ActionType.CREATE, ActionType.UPDATE):
                    a[act.filename] = b[act.filename]
                elif act.action is ActionType.DELETE:
                    del a[act.filename]

        applied.append(act)

    return applied


# ---------------------------------------------------------------------------
# High-level operations
# ---------------------------------------------------------------------------


def status(
    a: MutableMapping,
    b: MutableMapping,
    *,
    manifest: dict[str, str] | None = None,
    hash_fn: Callable[[str], str] = content_hash,
) -> list[SyncAction]:
    """Compute sync status without making any changes.

    Returns classified actions showing what *would* happen on sync.
    """
    return reconcile(snapshot(a, hash_fn=hash_fn), snapshot(b, hash_fn=hash_fn), manifest=manifest)


def push(
    source: MutableMapping,
    target: MutableMapping,
    *,
    delete: bool = False,
    dry_run: bool = False,
    hash_fn: Callable[[str], str] = content_hash,
) -> list[SyncAction]:
    """One-directional: propagate *source* state to *target*.

    This is a "source wins" operation — no manifest needed.
    If *delete* is True, files in *target* that are absent from *source*
    are removed.
    """
    snap_src = snapshot(source, hash_fn=hash_fn)
    snap_tgt = snapshot(target, hash_fn=hash_fn)
    actions: list[SyncAction] = []

    all_keys = set(snap_src) | set(snap_tgt)
    for k in sorted(all_keys):
        in_src = k in snap_src
        in_tgt = k in snap_tgt

        if in_src and in_tgt:
            if snap_src[k] == snap_tgt[k]:
                actions.append(SyncAction(k, ActionType.NOOP, 'none', 'identical'))
            else:
                actions.append(SyncAction(
                    k, ActionType.UPDATE, 'a_to_b', 'content differs',
                    a_hash=snap_src[k], b_hash=snap_tgt[k],
                ))
        elif in_src:
            actions.append(SyncAction(
                k, ActionType.CREATE, 'a_to_b', 'missing in target',
                a_hash=snap_src[k],
            ))
        elif delete:
            actions.append(SyncAction(
                k, ActionType.DELETE, 'a_to_b', 'not in source, deleting from target',
                b_hash=snap_tgt[k],
            ))
        else:
            actions.append(SyncAction(
                k, ActionType.NOOP, 'none', 'extra in target (kept)',
                b_hash=snap_tgt[k],
            ))

    return propagate(actions, source, target, dry_run=dry_run)


def pull(
    target: MutableMapping,
    source: MutableMapping,
    *,
    delete: bool = False,
    dry_run: bool = False,
    hash_fn: Callable[[str], str] = content_hash,
) -> list[SyncAction]:
    """One-directional: propagate *source* state into *target*.

    Convenience wrapper — same as ``push(source, target, ...)``.
    """
    return push(source, target, delete=delete, dry_run=dry_run, hash_fn=hash_fn)


def sync(
    a: MutableMapping,
    b: MutableMapping,
    *,
    manifest: dict[str, str] | None = None,
    manifest_path: str | Path | None = None,
    on_conflict: ConflictPolicy | Callable[[SyncAction], SyncAction] = ConflictPolicy.RAISE,
    dry_run: bool = False,
    hash_fn: Callable[[str], str] = content_hash,
) -> list[SyncAction]:
    """Bidirectional sync with three-way reconciliation.

    Requires a *manifest* (or *manifest_path*) for correct conflict detection.
    If neither is provided, uses an empty manifest (first sync — everything
    looks "created").

    After successful propagation, updates the manifest to reflect the new
    synchronized state.
    """
    if manifest is None and manifest_path is not None:
        manifest = load_manifest(manifest_path)
    if manifest is None:
        manifest = {}

    snap_a = snapshot(a, hash_fn=hash_fn)
    snap_b = snapshot(b, hash_fn=hash_fn)
    actions = reconcile(snap_a, snap_b, manifest=manifest)
    actions = resolve_conflicts(actions, on_conflict=on_conflict)
    applied = propagate(actions, a, b, dry_run=dry_run)

    if not dry_run:
        # Build new manifest from the now-synchronized state
        new_manifest = snapshot(a, hash_fn=hash_fn)
        if manifest_path is not None:
            save_manifest(new_manifest, path=manifest_path)

    return applied


def clone(
    source: MutableMapping,
    target: MutableMapping,
    *,
    manifest_path: str | Path | None = None,
    hash_fn: Callable[[str], str] = content_hash,
) -> list[SyncAction]:
    """Initial copy: replicate *source* into *target*, creating a manifest.

    Clears *target* first, then copies all content from *source*.
    """
    # Clear target
    for k in list(target):
        del target[k]

    # Copy all
    actions: list[SyncAction] = []
    for k in source:
        target[k] = source[k]
        actions.append(SyncAction(
            k, ActionType.CREATE, 'a_to_b', 'cloned from source',
            a_hash=hash_fn(source[k]),
        ))

    if manifest_path is not None:
        save_manifest(snapshot(source, hash_fn=hash_fn), path=manifest_path)

    return actions
