---
name: aikb-sync
description: "Use when syncing knowledge files between platforms or directories — e.g., pushing local files to Claude Projects, mirroring between projects, or batch-updating a knowledge base from a folder of markdown files."
---

# aikb: Sync Knowledge Files

Use this skill when syncing, mirroring, or batch-managing knowledge files across platforms or directories.

## Sync module (`aikb/sync.py`)

The sync engine operates on any two `MutableMapping` instances — plain dicts, `LocalKb`, `ClaudeProject`, dol stores, etc. Zero external dependencies (stdlib only).

### Core functions

| Function | Purpose | Manifest needed? |
|----------|---------|:----------------:|
| `push(source, target)` | One-directional: source wins | No |
| `pull(target, source)` | One-directional: source wins (reversed push) | No |
| `clone(source, target)` | Initial copy + manifest creation | Creates one |
| `sync(a, b, manifest=...)` | Bidirectional three-way reconciliation | Yes |
| `status(a, b)` | Read-only diff (no changes) | Optional |
| `snapshot(store)` | Return `{filename: content_hash}` | N/A |
| `reconcile(snap_a, snap_b, manifest=...)` | Low-level: classify actions | N/A |

### Key types

- `SyncAction` — dataclass: `filename`, `action` (ActionType), `direction`, `reason`
- `ActionType` — enum: `CREATE`, `UPDATE`, `DELETE`, `CONFLICT`, `NOOP`
- `ConflictPolicy` — enum: `RAISE`, `SKIP`, `A_WINS`, `B_WINS`
- `SyncConflictError` — raised when conflicts exist and policy is `RAISE`

## Common patterns

### Push local files to Claude Project

```python
from aikb import LocalKb, ClaudeProject, push

local = LocalKb('/path/to/docs')
remote = ClaudeProject('project-uuid')

push(local, remote)                # copy new/changed files
push(local, remote, delete=True)   # also remove remote extras
push(local, remote, dry_run=True)  # preview without applying
```

### Pull from Claude Project to local

```python
from aikb import pull

pull(local, remote)                # remote → local
pull(local, remote, delete=True)   # also remove local extras
```

### Bidirectional sync with manifest

```python
from aikb import clone, sync

# First time: clone establishes the manifest (baseline snapshot)
clone(local, remote, manifest_path='.aikb/manifest.json')

# Later: three-way reconciliation detects who changed what
sync(local, remote, manifest_path='.aikb/manifest.json')
```

Without a manifest, `sync` treats everything as "created" (first-sync behavior). The manifest stores `{filename: content_hash}` and is updated after each successful sync.

### Check status without making changes

```python
from aikb import status

actions = status(local, remote)
for a in actions:
    if a.action.value != 'noop':
        print(f"{a.action.value:8s} {a.direction:10s} {a.filename} — {a.reason}")
```

### Conflict resolution

```python
from aikb import sync, ConflictPolicy

# Built-in policies
sync(a, b, manifest=m, on_conflict=ConflictPolicy.A_WINS)
sync(a, b, manifest=m, on_conflict=ConflictPolicy.B_WINS)
sync(a, b, manifest=m, on_conflict=ConflictPolicy.SKIP)

# Custom callable: receives SyncAction, returns resolved SyncAction
def my_resolver(action):
    print(f"Conflict on {action.filename}, keeping A's version")
    return SyncAction(action.filename, ActionType.UPDATE, 'a_to_b', 'user chose A')

sync(a, b, manifest=m, on_conflict=my_resolver)
```

### Works with plain dicts

```python
from aikb import push, sync, snapshot

a = {"readme.md": "# Hello", "notes.md": "Some notes"}
b = {}
push(a, b)  # b is now a copy of a
```

### Selective sync with filtering

```python
# Only sync markdown files: use a filtered dict
md_files = {k: local[k] for k in local if k.endswith('.md')}
push(md_files, remote)
```

### Mirror between two projects

```python
from aikb import ClaudeProject, push

proj_a = ClaudeProject('uuid-a')
proj_b = ClaudeProject('uuid-b')
push(proj_a, proj_b, delete=True)  # exact mirror
```

## Legacy: sync_folder.py helper script

The script at `.claude/skills/aikb-sync/scripts/sync_folder.py` predates `aikb.sync` and provides a CLI for one-directional local→Claude sync. For new work, prefer `aikb.push()` / `aikb.pull()` directly.

## Using ClaudeProjects for discovery

```python
from aikb import ClaudeProjects

projects = ClaudeProjects()
for name in projects:
    files = projects[name]
    print(f"{name}: {list(files)}")
```
