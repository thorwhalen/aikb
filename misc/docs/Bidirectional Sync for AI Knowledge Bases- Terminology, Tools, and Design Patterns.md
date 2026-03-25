# Bidirectional Sync for AI Knowledge Bases: Terminology, Tools, and Design Patterns

**Author:** Thor Whalen  
**Date:** March 25, 2026

---

## Executive Summary

This report maps the terminology and tools of **bidirectional file synchronization** onto the problem of keeping local folders in sync with AI project knowledge bases (Claude Projects, Gemini Gems, GitHub). The goal is to inform the architecture of `aikd` — a thin Python facade that provides git-like clone/push/pull semantics over heterogeneous backends, backed by `dol` Mapping interfaces.

The research identifies three Python libraries with directly applicable architectures: **DiffSync** (Network to Code) for abstract dataset reconciliation, **pyftpsync** for its pluggable `_Target` pattern, and **ClaudeSync** as the proven Claude Projects API client. A critical discovery is that **Gemini Gems automatically create a dedicated Google Drive folder** for knowledge files, and when files are referenced from Drive, the Gem uses the most recent version — making Google Drive the actual sync target for Gems, solvable via **PyDrive2** or **rclone**.

The core sync algorithm is well-established: a **three-way reconciliation** comparing each replica against a stored **manifest** (baseline/archive) to produce a set of **sync actions** with conflict detection. This pattern has been stable since Unison formalized it in 1998.

---

## 1. Canonical Terminology

The file synchronization domain has a mature vocabulary, formalized primarily by the **Unison file synchronizer** [1] and reinforced by distributed version control systems (git, Mercurial). Here is the canonical mapping for the `aikd` project:

### Core Concepts

| Term | Definition | `aikd` equivalent |
|---|---|---|
| **Replica** | A complete copy of a set of files at a specific location [1][6] | A local folder, a Claude Project, a Gemini Gem's Drive folder, a GitHub repo |
| **Sync pair** | A tracked bidirectional relationship between two replicas | `local ↔ claude`, `local ↔ github`, `local ↔ gdrive` |
| **Working tree** | The local replica where the user directly edits files | `ai_knowledge/` root directory |
| **Remote** | A named reference to a non-local replica (analogous to git's `origin`) | A Claude Project ID, a Gem ID, a GitHub repo URL |
| **Tracking** | The association between a local directory and a specific remote | Stored in `.aikd/remotes.toml` |
| **Manifest** / **Archive** / **Baseline** | A snapshot of the last-known-common state between two replicas: file listing with content hashes [1][7] | JSON file per sync pair in `.aikd/manifests/` |
| **Reconciliation** | Comparing both replicas' current state against the manifest to classify each file [1][7] | The core `reconcile()` function |
| **Sync action** | A classified operation: `create`, `update`, `delete`, or `conflict`, with a direction (local→remote or remote→local) | A list of `SyncAction` dataclass instances |
| **Conflict** | When the same file has been modified in both replicas since the last sync [1][3] | Requires user decision or a conflict resolution strategy |
| **Propagation** | Executing the sync actions — performing the actual writes/deletes [1] | The `propagate()` function |
| **Conflict resolution strategy** | Policy for resolving conflicts: `ask`, `newest-wins`, `local-wins`, `remote-wins`, `keep-both` [12][16] | A callable or enum passed to the sync engine |

### Operations (git-inspired)

| Operation | Definition | Sync semantics |
|---|---|---|
| **Clone** | Initial copy from remote to local, establishing tracking + first manifest | One-time full download + manifest creation |
| **Pull** | Propagate remote changes to local (with conflict detection) | `diff(manifest, remote)` → apply non-conflicting to local |
| **Push** | Propagate local changes to remote (with conflict detection) | `diff(manifest, local)` → apply non-conflicting to remote |
| **Sync** (bidirectional) | Simultaneously propagate changes in both directions | Full three-way reconciliation |
| **Status** | Show what has changed locally and/or remotely since last sync | `diff(manifest, local)` + `diff(manifest, remote)` without propagation |
| **Diff** | Show the detailed differences for specific files | Content-level comparison |

### The Three-Way Reconciliation Algorithm

This is the fundamental algorithm used by Unison [1], pyftpsync [12], syncrclone [18], and virtually every correct bidirectional sync tool. Given two replicas A and B, and a manifest M recording their last synchronized state:

```
For each filename across union(A, B, M):

  in_A = filename exists in A (with hash_A)
  in_B = filename exists in B (with hash_B)  
  in_M = filename exists in M (with hash_M)

  Case 1: in_M, in_A, in_B
    - hash_A == hash_M and hash_B == hash_M → no change (skip)
    - hash_A != hash_M and hash_B == hash_M → A modified, propagate A→B
    - hash_A == hash_M and hash_B != hash_M → B modified, propagate B→A
    - hash_A != hash_M and hash_B != hash_M → CONFLICT (both modified)

  Case 2: in_M, in_A, not in_B → B deleted it. Action: delete from A (or conflict)
  Case 3: in_M, not in_A, in_B → A deleted it. Action: delete from B (or conflict)
  Case 4: in_M, not in_A, not in_B → both deleted (skip, remove from manifest)

  Case 5: not in_M, in_A, in_B → both created (conflict if different, skip if same)
  Case 6: not in_M, in_A, not in_B → A created. Propagate A→B
  Case 7: not in_M, not in_A, in_B → B created. Propagate B→A
```

Without the manifest, the algorithm degrades to naive two-way comparison and **cannot distinguish "created on A" from "deleted on B"** — which is why Unison, pyftpsync, and syncrclone all persist a manifest [7][12][18]. This is the single most important data structure in the system.

The manifest should contain, per file: `{filename: str, content_hash: str, size: int, mtime: float}`. Content hashes (SHA-256 or similar) are preferred over timestamps for correctness, since cloud APIs may not preserve modification times [18].

---

## 2. Python Sync Libraries and Architectural Patterns

### 2.1 DiffSync (Network to Code)

**DiffSync** [31] is the most architecturally relevant library for `aikd`. It is a Python library (Apache 2.0, ~400+ GitHub stars, maintained by Network to Code / Nautobot team, latest release 2.2.0) for comparing and synchronizing **arbitrary structured datasets** — not just files. Its key abstractions:

- **`DiffSyncModel`**: A Pydantic-based data model with `_identifiers` (natural key), `_attributes` (syncable fields), and `_children`. Each instance is uniquely identified by its identifiers [35].
- **`Adapter`** (formerly `DiffSync`): A container that loads data from a specific source into `DiffSyncModel` instances. You write one adapter per data source [35].
- **`diff_to()` / `diff_from()`**: Produces a structured `Diff` object showing creates, updates, and deletes between two adapters [32].
- **`sync_to()` / `sync_from()`**: Executes the diff and calls `create()`, `update()`, `delete()` methods on the target adapter's models [32].

DiffSync is designed for the **exact pattern** `aikd` needs: define a `KnowledgeFile` model, write a `LocalAdapter`, `ClaudeProjectAdapter`, `GDriveAdapter`, and let DiffSync handle the reconciliation. However, DiffSync does **not** maintain a manifest — it compares two live snapshots. For full bidirectional sync with conflict detection, you'd need to layer the manifest on top.

**Relevance to `aikd`**: DiffSync's `Adapter` pattern maps cleanly to `dol` stores. The adapter's `load()` fills the model from the store; the model's `create()`/`update()`/`delete()` write back. DiffSync handles the diff/sync logic. The missing piece — persistent manifest for three-way reconciliation — can be added as a thin wrapper.

### 2.2 pyftpsync

**pyftpsync** [12][20] (MIT license, Python, ~200 stars, maintained since 2012) provides bidirectional sync between filesystems and FTP/SFTP servers. Its architecture is the closest to what `aikd` needs at the file-sync level:

- **`_Target`** base class: Abstract interface with methods like `open_readable()`, `write_file()`, `remove_file()`, `get_dir()`, `read_text()`. Subclasses: `FsTarget` (local filesystem), `FTPTarget` (FTP), `SFTPTarget` (SFTP) [51][53].
- **`BaseSynchronizer`** with subclasses: `UploadSynchronizer`, `DownloadSynchronizer`, `BiDirSynchronizer` [59].
- **`DirMetadata`**: Stores sync metadata (modification times, sizes) in hidden files within each synced directory — this is effectively a per-directory manifest [56].
- **`make_target(url)`**: Factory function that creates the appropriate `_Target` from a URL scheme [53].

The `_Target` abstraction is particularly instructive: it is essentially a `MutableMapping` over files in a directory tree, with additional metadata operations. A `ClaudeProjectTarget` or `GDriveTarget` could implement this interface.

**Key design insight from pyftpsync**: It stores metadata (manifest) **inside the local folders** as hidden files (`.pyftpsync-meta.json`), not in a central database. This is portable and self-contained — the sync state travels with the directory [56].

### 2.3 SyncEngine

**SyncEngine** [16][21] (Python, available on PyPI) is a more recent sync library with:

- **Pluggable storage interfaces**: "Protocol Agnostic" — works with any storage backend [16].
- **Multiple sync modes**: `TWO_WAY`, `SOURCE_TO_DESTINATION`, `SOURCE_BACKUP`, etc. [16].
- **Persistent state tracking**: Maintains state across sessions, supports resuming interrupted syncs [16].
- **Conflict resolution strategies**: `newest_wins`, `source_wins`, `destination_wins`, `manual` [16].

Less documented and less starred than DiffSync or pyftpsync, but its "pluggable storage interface" claim makes it worth evaluating. The sync modes map directly to `aikd`'s push/pull/sync operations.

### 2.4 syncrclone / rclone bisync

**syncrclone** [18] (Python, MIT) was a standalone Python tool for bidirectional sync using rclone as the transport layer. As of rclone v1.58.0, rclone itself has a native `bisync` command [44]. The algorithm is notable for its simplicity: matching files are removed from consideration first, then moves are tracked only for files that are new, match a previous file, and are marked for deletion on the other side [18].

**rclone** itself [48] provides an HTTP API (`rclone rc`) for programmatic control, and Python wrappers exist: **rclone-python** [45] (simple subprocess wrapper) and **rclone-api** [42] (more comprehensive, with `DiffItem`, `DiffOption` types). Since rclone natively supports Google Drive, it could serve as the transport layer for the Gemini Gems path (via Google Drive).

### 2.5 Summary: Architectural Patterns Across Libraries

| Library | Target/Adapter abstraction | Manifest/state storage | Conflict handling | Bidirectional |
|---|---|---|---|---|
| **DiffSync** | `Adapter` + `DiffSyncModel` | None (live comparison only) | Via model callbacks | Yes (diff_to/sync_to) |
| **pyftpsync** | `_Target` base class | `.pyftpsync-meta.json` in dirs | Interactive + strategies | Yes (`BiDirSynchronizer`) |
| **SyncEngine** | Pluggable storage interface | Persistent state DB | Strategy enum | Yes (TWO_WAY mode) |
| **syncrclone** | rclone remotes | Previous file listing | Configurable | Yes |
| **Unison** | Filesystem replicas | `~/.unison/` archive | Interactive | Yes |

---

## 3. Backend-Specific Findings

### 3.1 Claude Projects → ClaudeSync

**ClaudeSync** [previous report] remains the only viable path. It communicates with `api.claude.ai` using session keys and provides full CRUD on project knowledge files. Its internal provider module handles organization discovery, project enumeration, file upload with checksums, and error recovery. For `aikd`, ClaudeSync should be used as a **dependency** — its API client wraps months of reverse-engineering work.

The key operations needed from ClaudeSync's API:
- List organizations → list projects → list files (with content hashes)
- Create file (upload content)
- Update file (re-upload content, matched by filename)
- Delete file
- Read file content

### 3.2 Gemini Gems → Google Drive

**Critical finding**: Gemini Gems that have knowledge files create a **dedicated Google Drive folder** to store them [63][64][69]. Google's announcement states: "When referencing files from Drive, Gems use the most recent version of that file so it's always up-to-date" [63]. This means:

1. **Google Drive IS the sync target for Gems**, not the Gemini web UI.
2. Updating files in the Gem's Drive folder automatically updates the Gem's knowledge.
3. No browser automation needed — standard Google Drive API works.

The path is: `local ↔ Google Drive folder ↔ Gemini Gem` (the second link is automatic).

**PyDrive2** [81] (maintained by the DVC team, MIT license, supports fsspec) provides clean CRUD for Google Drive:
```python
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
gauth = GoogleAuth()
drive = GoogleDrive(gauth)
file = drive.CreateFile({'title': 'ideas.md', 'parents': [{'id': gem_folder_id}]})
file.SetContentString("# Ideas\n...")
file.Upload()
```

PyDrive2 also provides `GDriveFileSystem` (fsspec-compatible), which could integrate with `dol` stores.

**Alternative**: rclone with its native Google Drive support could handle the sync transport, with the rclone-python wrapper [45] for programmatic control.

**Caveat**: Gems currently support **up to 10 files**, each up to 100 MB [70]. Files can be uploaded locally or referenced from Drive [65]. The Drive-linked approach is strongly preferred since updates propagate automatically.

### 3.3 GitHub → git

This is the simplest leg: standard git operations. The `ai_knowledge/` directory is a git repository. `gitpython` or subprocess calls to `git` handle push/pull/commit. Git provides full version control, making data loss from sync errors recoverable.

The key insight: git operations on the local folder happen **after** syncing with Claude/Gemini. The workflow is:
1. `aikd pull claude/my-project` — pull remote changes to local
2. `git add . && git commit` — version control the changes
3. `aikd push claude/my-project` — push local changes to remote
4. `git push` — backup to GitHub

---

## 4. Recommended Architecture for `aikd`

### 4.1 Layer 1: Store Abstraction (`dol`-compatible)

Each backend is a `MutableMapping[str, str]` where keys are filenames and values are file contents. This maps directly to `dol.Store`:

```python
from collections.abc import MutableMapping

class BaseProjectStore(MutableMapping):
    """Abstract base for AI project knowledge file stores."""
    
    def snapshot(self) -> dict[str, str]:
        """Return {filename: content_hash} for all files."""
        ...
    
    # __getitem__, __setitem__, __delitem__, __iter__, __len__
    # implemented by subclasses
```

Concrete implementations:
- `LocalFileStore(path)` — trivial, wraps `pathlib.Path`
- `ClaudeProjectStore(session_key, org_id, project_id)` — wraps ClaudeSync's API client
- `GDriveStore(credentials, folder_id)` — wraps PyDrive2

### 4.2 Layer 2: Sync Engine

The sync engine operates on pairs of stores + a manifest:

```python
@dataclass
class SyncAction:
    filename: str
    action: Literal['create', 'update', 'delete']
    direction: Literal['local_to_remote', 'remote_to_local']
    reason: str  # e.g., "modified locally", "created remotely"

@dataclass  
class Conflict:
    filename: str
    local_hash: str | None
    remote_hash: str | None
    manifest_hash: str | None

def reconcile(
    local: BaseProjectStore,
    remote: BaseProjectStore, 
    manifest: dict[str, str]
) -> tuple[list[SyncAction], list[Conflict]]:
    """Three-way reconciliation. Returns actions and conflicts."""
    ...
```

The reconcile function implements the algorithm from Section 1. Non-conflicting actions can be auto-applied; conflicts are surfaced to the user.

### 4.3 Layer 3: CLI / MCP Interface

```
aikd clone claude <project-name>     # Clone a Claude project locally
aikd clone gemini <gem-name>         # Clone a Gemini Gem's Drive folder
aikd status [path]                   # Show what changed since last sync
aikd pull [path]                     # Pull remote changes (with conflict warnings)
aikd push [path]                     # Push local changes (with conflict warnings)
aikd sync [path]                     # Bidirectional sync
aikd list claude                     # List available Claude projects
aikd list gemini                     # List available Gems
```

### 4.4 The DiffSync Question

There are two viable approaches for the sync engine layer:

**Option A: Build on DiffSync.** Define a `KnowledgeFile(DiffSyncModel)` with `_identifiers=("filename",)` and `_attributes=("content_hash", "size")`. Write adapters per backend. Add a manifest layer on top for three-way reconciliation. DiffSync handles the diff computation and action dispatch.

**Option B: Implement the reconciliation directly.** The three-way reconciliation algorithm is ~50 lines of code. The manifest is a JSON file. The sync actions are dataclasses. This avoids the DiffSync dependency (Pydantic, structlog) and keeps `aikd` minimal.

**Recommendation**: Option B. The algorithm is simple enough that adding DiffSync's abstraction layers (Pydantic models, adapter classes, `top_level` declarations) would add more boilerplate than it saves. The `dol` `MutableMapping` interface is already simpler and more Pythonic than DiffSync's adapter pattern. DiffSync shines for complex hierarchical data with parent-child relationships — but knowledge files are flat.

### 4.5 Dependency Summary

| Component | Dependency | Purpose |
|---|---|---|
| Claude Projects backend | `claudesync` (pip) | API client for `api.claude.ai` |
| Google Drive backend | `pydrive2` (pip) | Google Drive CRUD |
| Local filesystem | stdlib (`pathlib`) | File I/O |
| Git operations | `gitpython` or subprocess | Version control |
| Manifest storage | stdlib (`json`, `hashlib`) | Baseline snapshots |
| MCP exposure (optional) | `fastmcp` (pip) | Tool exposure for Claude Code/Desktop |

---

## 5. Filesystem Layout

```
ai_knowledge/                        ← git repo root
├── .aikd/                           ← sync metadata (gitignored selectively)
│   ├── config.toml                  ← global config (default conflict policy, etc.)
│   ├── remotes/                     ← remote definitions
│   │   ├── claude__my-project.toml  ← {org_id, project_id, session_key_ref}
│   │   └── gemini__my-gem.toml      ← {folder_id, credentials_ref}
│   └── manifests/                   ← per-sync-pair baselines
│       ├── claude__my-project.json  ← {filename: {hash, size, synced_at}}
│       └── gemini__my-gem.json
├── claude/                          ← provider namespace
│   └── my-project/                  ← tracked project
│       ├── files/                   ← knowledge files (synced content)
│       │   ├── contents.md
│       │   └── ideas.md
│       └── instructions.md          ← (future: project system prompt)
├── gemini/
│   └── my-gem/
│       └── files/                   ← knowledge files (synced via Drive)
├── .gitignore                       ← ignore .aikd/remotes/ (secrets), keep manifests
└── .git/
```

**Key decisions:**
- Manifests are **committed to git** — they travel with the repo and enable any machine to know the last-synced state.
- Remote configs (containing session keys, credentials) are **gitignored** — secrets stay local.
- The `files/` subdirectory convention separates knowledge files from future extensions (instructions, parameters, etc.).

---

## 6. The Gemini Gems → Google Drive Path in Detail

The discovery that Gems use Google Drive folders as storage backends [63][64][69] changes the entire Gemini approach. Instead of browser automation, the workflow is:

1. **Setup**: User creates a Gem in Gemini UI, adds files via Google Drive (referencing a specific folder). This creates the Drive ↔ Gem link.
2. **Clone**: `aikd` queries Google Drive API for the Gem's folder contents, downloads to local `gemini/my-gem/files/`.
3. **Sync**: Standard bidirectional file sync against the Google Drive folder via PyDrive2.
4. **Auto-update**: Because the Gem references Drive files, it automatically sees the latest versions [63].

**Remaining challenge**: Programmatically discovering which Google Drive folder is linked to which Gem. The gemini-webapi library can list Gems and their metadata, but the Drive folder ID linkage may require manual configuration initially. Users can find it in Drive under a Gem-named folder [64].

---

## 7. Open Questions for Implementation

1. **Manifest granularity**: Should manifests store content hashes only, or also content (for offline diff display)? Content hashes are sufficient for sync; full content enables richer `aikd status` output but increases storage.

2. **Conflict UI**: For CLI usage, pyftpsync's interactive mode (prompt per conflict) is the standard [12]. For MCP/agent usage, a policy enum (`ask`, `newest`, `local`, `remote`) is cleaner. Support both.

3. **Auto-sync**: rclone-bisync-manager [43] demonstrates daemon-based auto-sync with cron schedules. This could be a Phase 2 feature — `aikd watch` using filesystem events (watchdog) + periodic remote polling.

4. **Claude Project instructions sync**: Claude Projects have both knowledge files and a system prompt ("custom instructions"). The system prompt is a separate API call in ClaudeSync. It maps naturally to `instructions.md` in the local folder.

5. **Atomicity**: Cloud APIs may fail mid-sync. pyftpsync handles this by writing metadata only after successful file transfer [56]. `aikd` should update the manifest only after all propagations succeed — or implement per-file manifest updates with a transaction log.

---

## REFERENCES

[1] B.C. Pierce. [Unison File Synchronizer](https://github.com/bcpierce00/unison). GitHub, maintained since 1998.

[3] [Unison (software)](https://en.wikipedia.org/wiki/Unison_(software)). Wikipedia.

[6] [A Modern Unison File Sync Alternative](https://www.resilio.com/blog/a-modern-unison-file-sync-alternative). Resilio, 2022.

[7] [File synchronisation algorithms](https://ianhowson.com/blog/file-synchronisation-algorithms/). Ian Howson.

[12] M. Wendt. [pyftpsync](https://pyftpsync.readthedocs.io/). Python library for FTP/SFTP/filesystem sync. MIT license.

[16] [SyncEngine](https://syncengine.readthedocs.io/en/latest/). Python sync engine with pluggable storage.

[17] J. Wink. [PyFiSync](https://github.com/Jwink3101/PyFiSync). Python file sync with backup and move tracking.

[18] J. Wink. [syncrclone](https://github.com/Jwink3101/syncrclone). Python bidirectional sync for rclone.

[20] M. Wendt. [pyftpsync GitHub](https://github.com/mar10/pyftpsync).

[31] Network to Code. [DiffSync](https://github.com/networktocode/diffsync). Python library for comparing and synchronizing datasets.

[32] Network to Code. [Introduction to Diffing and Syncing Data with DiffSync](https://networktocode.com/blog/intro-to-diffing-and-syncing-data-with-diffsync/). Blog post, 2024.

[35] [diffsync on PyPI](https://pypi.org/project/diffsync/1.3.0/).

[42] [rclone-api](https://github.com/zackees/rclone-api). Python Rclone API bindings.

[43] [rclone-bisync-manager](https://github.com/Gunther-Schulz/rclone-bisync-manager). Daemon-based manager for rclone bisync.

[44] rclone. [Bisync](https://rclone.org/bisync/). Official bidirectional sync command (v1.58.0+).

[45] [rclone-python](https://pypi.org/project/rclone-python/). Python wrapper for rclone.

[48] rclone. [Remote Control / API](https://rclone.org/rc/).

[63] Google. [New features in Gemini — Gems with deeper knowledge](https://workspace.google.com/blog/product-announcements/new-gemini-gems-deeper-knowledge-and-business-context). Google Workspace Blog, Nov 2024.

[64] [Gemini Knowledge Base Fix: Documents Disappearing](https://workalizer.com/insights/gemini/gemini-knowledge-base-glitch-documents-disappearing-how-to-secure-your-files-and-find-them-on-google-drive/). Workalizer.

[65] Google. [Upload Google Docs and other file types to Gem instructions](https://workspaceupdates.googleblog.com/2024/11/upload-google-docs-and-other-file-types-to-gems.html). Nov 2024.

[69] [Fix Gemini Gem Knowledge Disappearing](https://workalizer.com/blog/apps-tools/gemini-gems-forgetting-documents-how-to-fix-disappearing-knowledge-in-google-workspace/). Workalizer.

[70] [Google Gemini Gems Now Supports File Uploads](https://techwiser.com/google-gemini-gems-now-supports-file-uploads-to-its-knowledge/). TechWiser, Nov 2024.

[75] [The Magic of 3-Way Merge](https://blog.git-init.com/the-magic-of-3-way-merge/). Git Init, 2024.

[76] N. Fraser. [Differential Synchronization](https://neil.fraser.name/writing/sync/).

[79] [Merge (version control)](https://en.wikipedia.org/wiki/Merge_(version_control)). Wikipedia.

[81] Iterative. [PyDrive2](https://github.com/iterative/PyDrive2). Google Drive API Python wrapper. MIT license.
