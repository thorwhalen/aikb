# aikb — Project Instructions

## What this is

`aikb` provides programmatic CRUD for AI project knowledge bases (Claude Projects, Gemini Gems) via a `MutableMapping` interface compatible with `dol`.

## Architecture

**`aikb/base.py`** — CRUD layer:
- **Provider protocol** (`KnowledgeBaseProvider`) — structural typing, no inheritance
- **Store facade** (`KnowledgeFiles`) — `collections.abc.MutableMapping`
- **Factory functions** (`LocalKb`, `ClaudeProject`) — progressive disclosure
- **Collection mapping** (`ClaudeProjects`) — `Mapping` of project names → `KnowledgeFiles`

**`aikb/sync.py`** — Sync engine (stdlib only, decoupled from base.py):
- Operates on any two `MutableMapping` instances
- `push()`, `pull()`, `clone()`, `sync()`, `status()` — git-inspired operations
- Three-way reconciliation with manifest for bidirectional sync
- Conflict detection with pluggable resolution (`ConflictPolicy` enum or callable)

Optional `aikb/mcp_server.py` exposes CRUD as MCP tools.

## Skills

Load the relevant skill when working in these areas:

- **Maintaining/extending aikb code**: Read `.claude/skills/aikb-maintain/SKILL.md`
- **Helping users install/configure aikb**: Read `.claude/skills/aikb-setup/SKILL.md`
- **Syncing files between platforms**: Read `.claude/skills/aikb-sync/SKILL.md`

## Key conventions

- Provider methods raise `KeyError` on missing files
- `list_files` / `__iter__` yield (generators, not lists)
- Optional deps (`claudesync`, `fastmcp`, `browser_cookie3`) are lazy-imported via `_check_dependency()`
- Session key resolution is automatic: explicit → env var → ClaudeSync config → browser cookies
- All arguments after the first positional are keyword-only
- Zero core dependencies — extras for `claude`, `cookies`, `mcp`, `dol`
