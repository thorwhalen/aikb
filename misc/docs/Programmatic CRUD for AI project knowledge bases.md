# Programmatic CRUD for AI project knowledge bases

**Neither Anthropic nor Google exposes official APIs for managing knowledge files in Claude Projects or Gemini Gems.** Every existing tool relies on reverse-engineered, undocumented internal web APIs or browser automation — and for Gemini Gems knowledge files specifically, no programmatic path exists at all, even unofficially. This means the "build it yourself" path is unavoidable, but a strong foundation already exists: ClaudeSync (694 GitHub stars, actively maintained) proves the Claude.ai internal API is viable for full CRUD, and the MCP + `dol` Mapping pattern can unify heterogeneous backends into a clean facade. The recommended architecture is a thin Python facade wrapping ClaudeSync's proven API client for Claude Projects, Playwright-based browser automation for Gemini Gems, and FastMCP for tool exposure — all behind a `MutableMapping` interface compatible with `dol`.

---

## 1. The landscape of existing tools

The ecosystem splits sharply: Claude Projects has several community tools at varying maturity levels, while Gemini Gems has almost nothing.

### Claude Projects tools

**ClaudeSync** (jahwag/ClaudeSync) is the clear leader. It's a Python CLI tool with **694 stars, 70 forks, 12 contributors, and 44 releases** through v0.7.6 (March 8, 2026). It authenticates via session keys extracted from browser cookies and communicates with Claude.ai's internal web API at `api.claude.ai/api/organizations/{org_id}/...`. It supports full CRUD: `claudesync push` syncs local files to a project's knowledge base (create/update), `claudesync project truncate` deletes all remote files, and it can list projects and files. Checksum-based diffing avoids redundant uploads. The tool is well-documented with a wiki, Discord community, and CI/CD pipeline. Its primary limitation is one-way sync (local → cloud only) and reliance on session keys that expire, requiring periodic re-authentication.

A VS Code extension (rexdotsh/claudesync-vscode, ~20 stars) brings the same session-token approach into the IDE. An Electron desktop app (bob6664569/claude-sync) offers a GUI with magic-link authentication. Several Chrome extensions handle partial operations: **Claude Helper** does bulk folder upload and "quick project reset" (delete all files); **Claude Folder Upload Helper** preserves directory structure during upload; **Claude Project Downloader** exports knowledge files as ZIP. None of these offer headless/scriptable access.

No MCP server exists for Claude Project knowledge file management. A search across mcp.so (18,905+ indexed servers), awesome-mcp-servers, and multiple MCP directories turned up nothing. The closest was `davidteren/claude-server` for persistent context, which is now deprecated in favor of Claude Code's native CLAUDE.md system.

### Gemini Gems tools

**gemini-webapi** (HanaokaYuzu/Gemini-API) is the only relevant tool, with **~1,800–2,400 stars** and active maintenance through v1.21.0 (March 2026). It reverse-engineers the Gemini web app using browser cookies (`__Secure-1PSID`, `__Secure-1PSIDTS`) and supports full CRUD on Gem *instructions* (system prompts): `create_gem()`, `fetch_gems()`, `update_gem()`, `delete_gem()`. However, **it cannot manage Gem knowledge files** — the uploaded documents attached to a Gem have no known programmatic surface, even in the reverse-engineered API.

### Automation platforms

Zapier, Make, and n8n all integrate with Claude's *developer API* (Messages API) — not Claude.ai's Projects feature. None offer Gemini Gems integration. The Anthropic API's Files endpoint (`/v1/files`) is a completely separate system from Project knowledge files.

| Tool | Platform | Type | C | R | U | D | Stars | Last active | Method |
|---|---|---|---|---|---|---|---|---|---|
| **jahwag/ClaudeSync** | Claude Projects | Python CLI | ✅ | ✅ | ✅ | ✅ | 694 | Mar 2026 | Internal API |
| **claudesync-vscode** | Claude Projects | VS Code ext | ✅ | ✅ | ✅ | — | 20 | Active | Internal API |
| **Claude Helper** | Claude Projects | Chrome ext | ✅ | — | — | ✅ | N/A | Active | DOM automation |
| **Claude Project Downloader** | Claude Projects | Chrome ext | — | ✅ | — | — | N/A | Active | DOM automation |
| **HanaokaYuzu/Gemini-API** | Gemini Gems | Python lib | ✅* | ✅* | ✅* | ✅* | ~2K | Mar 2026 | Internal API |

*\*Gem instructions only, not knowledge files*

---

## 2. Official API support is absent on both platforms

### Anthropic

The Anthropic API at `api.anthropic.com` provides a **Files API** (beta, header `anthropic-beta: files-api-2025-04-14`) with endpoints for uploading files (`POST /v1/files`), listing them, retrieving metadata, downloading content, and deleting them. Maximum file size is **500 MB**, with support for PDF, DOCX, TXT, CSV, Markdown, images, and more. But these files are scoped to the API workspace and used in Messages API calls — they are **entirely separate from Claude.ai Project knowledge files**. There are zero endpoints for creating, reading, updating, or deleting Projects or their knowledge bases. The API release notes through March 2026 contain no mention of a Projects API, and no public roadmap item addresses this gap.

### Google

The Gemini API at `generativelanguage.googleapis.com` offers a **Files API** (48-hour TTL, 2 GB per file, free), a **File Search API** (persistent RAG stores with embeddings), and a **Context Caching API**. None of these connect to Gemini Gems. A Google AI Developer Forum moderator confirmed in September 2024: *"The Gemini app does not have an API, nor API access to its Gems."* Users attempting to call `https://generativelanguage.googleapis.com/v1beta/gems/MY_GEM_ID/...` receive 404 errors. Forum threads requesting Gems API access span from September 2024 through at least July 2025 with no resolution. Google I/O 2025 developer materials made no mention of a Gems API.

---

## 3. Community demand is strong but unmet

Two GitHub issues on `anthropics/claude-code` crystallize the problem. **Issue #25833** ("Allow Claude Code & Cowork to access Claude Chat Project knowledge bases") describes maintaining parallel context systems — CLAUDE.md in Claude Code and knowledge files in Claude Projects — with manual copy-paste as the only bridge. The author proposes a new MCP server or CLI flag: `claude --project "My Project Name"`. **Issue #25983** requests specific CLI commands: `claude project upload --project <id> path/to/file.md`, `claude project list`, `claude project sync`. The author notes that *"the only way to get them into Claude web's project knowledge is manual drag-and-drop through the browser"* and that stale data leads to wrong figures in documents.

On the Gemini side, the Google AI Developers Forum thread on Gems API access has accumulated comments over **18+ months** without resolution. One user pleaded: *"Can we at least get MCP support if you guys aren't going to fix this!"* The Make.com community has an unresolved thread about calling Gems in automation workflows.

Simon Willison documented a workaround that sidesteps Projects entirely: pipe files through `files-to-prompt` into the `llm` CLI tool, using the API's context window directly. This works but is expensive compared to the $20/month web UI and loses the persistent project context.

The **architectural disconnect between Claude Code and Claude Projects** is a recurring theme. Claude Code's CLAUDE.md files are self-modifying, version-controlled, and locally managed — Claude can update its own knowledge. Claude Projects' knowledge files are static, uploaded manually, and invisible to Claude Code. Issue #25833 states: *"Context built in one Anthropic product is invisible to the other, even though they serve the same user working on the same projects."*

---

## 4. How adjacent systems solve this problem

### OpenAI: the gold standard for API-first file management

OpenAI's Assistants/Responses API provides the most complete model. Files are uploaded via `POST /v1/files`, organized into Vector Stores (`POST /v1/vector_stores`), and attached to assistants or used in API calls. The API handles parsing, chunking, and embedding automatically. A complete Python workflow:

```python
file = client.files.create(file=open("doc.pdf", "rb"), purpose="assistants")
vs = client.vector_stores.create(name="My Knowledge")
client.vector_stores.files.create(vector_store_id=vs.id, file_id=file.id)
```

Key design pattern: **two-layer abstraction** (raw files → processed vector stores). Storage costs $0.10/GB/day beyond 1 GB free. The Assistants API is deprecated (shutdown August 26, 2026) in favor of the Responses API with `file_search` tool.

### Claude Code: self-modifying knowledge as a design pattern

Claude Code's approach is the most architecturally interesting. CLAUDE.md files form a hierarchy: project root, subdirectories, `.claude/rules/`, and `~/.claude/CLAUDE.md` for user-level globals. The agent **reads and writes its own instruction files**, creating compounding knowledge across sessions. Auto Memory (v2.1.59+) lets Claude decide what's worth remembering. The `/memory` command provides browse/edit/delete. This self-modifying pattern is the closest analog to what a unified tool should enable for Claude Projects.

### Cursor, Windsurf, Continue.dev: filesystem-as-API

All three use **convention-over-configuration** with special files in the repository. Cursor uses `.cursor/rules/*.mdc` with glob-based activation. Windsurf separates auto-generated Memories (`~/.codeium/windsurf/memories/`) from user-defined Rules (`.windsurf/rules/`). Continue.dev offers the most extensible model: pluggable context providers via TypeScript, HTTP endpoints, or MCP servers. The key lesson: **markdown files in the repo ARE the knowledge API**, with the filesystem providing natural CRUD.

### Mem0 and Letta: dedicated memory layers

Mem0 (~48K GitHub stars) provides a full semantic memory API with `add()`, `search()`, `update()`, `delete()` — plus automatic extraction, deduplication, and temporal awareness. Letta (formerly MemGPT) uses an OS-inspired architecture: Core Memory (in-context, like RAM), Recall Memory (searchable history), and Archival Memory (long-term storage via tool calls). Both demonstrate that **the agent should manage its own memory through explicit API calls**.

---

## 5. Architecture for a unified tool

### The `dol` Mapping pattern as unifying abstraction

The `dol` package (i2mint/dol, MIT license, pure Python, zero dependencies) provides a `Store` class implementing `MutableMapping` with internal translation hooks. The key extension mechanism is `wrap_kvs`:

```python
from dol import wrap_kvs, Store

@wrap_kvs(
    id_of_key=lambda filename: f"projects/{project_id}/files/{filename}",
    obj_of_data=lambda data: data.decode('utf-8'),
    data_of_obj=lambda obj: obj.encode('utf-8')
)
class ClaudeProjectStore(Store):
    """Dict-like access to Claude Project knowledge files."""
    pass
```

This yields `store['ideas.md'] = "content"`, `del store['outdated-notes.md']`, `content = store['contents.md']` — exactly the interface the user specified. However, `dol` has only **4 GitHub stars** and limited documentation. The same pattern works with Python's standard `collections.abc.MutableMapping`, which avoids the niche dependency while preserving interface compatibility. Since the user already uses `dol`, wrapping the backends as `dol` stores is the right call — but implementing against `MutableMapping` first ensures the abstraction works without `dol` too.

### Recommended three-layer architecture

**Layer 1 — Backend providers** (one per platform):

- **`ClaudeProjectProvider`**: Wraps ClaudeSync's API client module. Session-key authentication against `api.claude.ai`. Full CRUD on project knowledge files. Reuses ClaudeSync's proven endpoint mappings and error handling rather than re-implementing them.
- **`GeminiGemProvider`**: Two options: (a) Playwright-based browser automation for knowledge files, or (b) gemini-webapi for instruction-only CRUD. For knowledge *file* management, Playwright is currently the only path.
- **`LocalFilesystemProvider`**: Standard file I/O. Serves as staging area, test backend, and fallback.

**Layer 2 — `dol` Store facade**:

```python
class AIKnowledgeStore(MutableMapping):
    """Unified dict-like interface to AI project knowledge bases."""
    def __init__(self, provider: BaseProvider, project_id: str):
        self.provider = provider
        self.project_id = project_id
    
    def __getitem__(self, filename: str) -> str:
        return self.provider.read_file(self.project_id, filename)
    
    def __setitem__(self, filename: str, content: str):
        self.provider.upsert_file(self.project_id, filename, content)
    
    def __delitem__(self, filename: str):
        self.provider.delete_file(self.project_id, filename)
    
    def __iter__(self):
        return iter(self.provider.list_files(self.project_id))
    
    def __len__(self):
        return len(self.provider.list_files(self.project_id))
```

**Layer 3 — MCP server** (FastMCP):

```python
from fastmcp import FastMCP

mcp = FastMCP("ai-knowledge-crud")

@mcp.tool()
def write_knowledge_file(platform: str, project: str, filename: str, content: str) -> dict:
    """Create or update a knowledge file in an AI project."""
    store = get_store(platform, project)
    store[filename] = content
    return {"status": "ok", "platform": platform, "project": project, "file": filename}
```

This exposes CRUD as MCP tools usable from Claude Desktop, Claude Code, Cursor, or any MCP-compatible client.

### Why ClaudeSync should be a dependency, not a reimplementation

ClaudeSync's `providers` module encodes months of reverse-engineering work: organization discovery, project enumeration, file upload with checksums, token refresh, and error handling for the undocumented `api.claude.ai` API. **Reimplementing this is wasted effort.** The facade should import ClaudeSync as a dependency (or vendor its provider module) and wrap it in the `dol` interface. ClaudeSync is MIT-licensed, pip-installable, and actively maintained.

---

## 6. Technical feasibility and key constraints

### Authentication

| Platform | Mechanism | Acquisition | Expiry | Risk |
|---|---|---|---|---|
| Claude.ai Projects | Session key (cookie) | Manual extraction from browser DevTools | Hours to days | ToS violation possible |
| Claude.ai Projects | OAuth token (`sk-ant-oat01-*`) | Claude Code subscription flow | Unknown | Tied to subscription, not Project management |
| Anthropic API | API key (`sk-ant-api-*`) | Console dashboard | None (until revoked) | No Project file access |
| Gemini Gems | Browser cookies (`__Secure-1PSID`) | Manual extraction or `browser_cookie3` | Days to weeks | ToS violation possible |
| Gemini API | API key | Google AI Studio | None | No Gems access |

**The session key for Claude.ai is the critical dependency.** ClaudeSync stores it with SSH key encryption and handles 403 re-authentication. For a Claude Code agent using this tool, the session key would need to be provided as an environment variable or stored in a config file.

### Platform constraints

Claude Projects accept files up to **30 MB each**, support PDF/DOCX/CSV/TXT/HTML/Markdown/code files, and hold content up to the **200K token context window** (switching to RAG retrieval when exceeded). ClaudeSync defaults to a **32 KB** per-file limit that is configurable. Gemini Gems support PDF/TXT/Markdown/DOCX/code/CSV/JSON/images, with files sourced from local upload or Google Drive. Neither platform publishes rate limits for their internal APIs, but ClaudeSync users report occasional 403 and 429 errors.

### Main blockers ranked by severity

**Critical**: Gemini Gems knowledge files have zero programmatic surface — even gemini-webapi can only manage instructions, not uploaded documents. Browser automation via Playwright is the sole viable path, and it is inherently fragile. **High**: Claude.ai's internal API is undocumented and can change without notice; ClaudeSync's issue tracker documents periodic breakages after Anthropic updates. **Medium**: Session token management adds user friction — manual cookie extraction is required on every expiry. **Low**: MCP and `dol` are well-understood layers with minimal risk.

---

## Recommended approach for implementation

The optimal path forward is a **thin facade package** with three components, ordered by implementation priority:

**Phase 1 — Claude Projects backend (highest value, proven feasibility):** Depend on ClaudeSync's API client. Wrap its provider in a `dol`-compatible `MutableMapping`. Expose via FastMCP server with `list_files`, `read_file`, `write_file`, `delete_file` tools. This gives a Claude Code agent the ability to manage Project knowledge files immediately. Estimated effort: **1–2 days** of implementation, mostly plumbing.

**Phase 2 — Local filesystem backend (immediate utility, trivial):** A local `MutableMapping` over a directory of markdown files. Useful as staging area ("draft this knowledge file locally, then push to Claude Project") and for testing. Essentially `pathlib.Path` operations behind the `dol` interface. Estimated effort: **hours**.

**Phase 3 — Gemini Gems backend (high value, high risk):** Start with gemini-webapi for instruction CRUD (proven). For knowledge file management, implement Playwright automation against `gemini.google.com`. Use accessibility snapshots rather than CSS selectors for resilience. Accept that this will be the most fragile component. Estimated effort: **3–5 days**, with ongoing maintenance.

**The tool should NOT attempt to replace ClaudeSync or gemini-webapi.** It should act as a **minimal facade** that unifies them behind `dol`'s `MutableMapping` interface and exposes them as MCP tools. The total codebase should be small — a few hundred lines of glue code connecting proven libraries to a clean abstraction. This is exactly the "thin facade over actively maintained tools" the user specified.

---

## Conclusion

The gap between what AI platforms offer in their UIs and what they expose via APIs is stark. **Claude Projects and Gemini Gems both lack official programmatic interfaces for knowledge file management**, and neither company has signaled plans to add them. The community has responded with reverse-engineered tools — ClaudeSync for Claude, gemini-webapi for Gemini — that prove the internal APIs work but carry ToS risk and fragility.

For a Python architect building a unified tool, the key insight is that **the hard work is already done**: ClaudeSync has battle-tested the Claude.ai internal API, and gemini-webapi has mapped the Gemini web app's endpoints. What's missing is the unifying abstraction layer. A `dol`-compatible `MutableMapping` store per backend, exposed through FastMCP, gives Claude Code agents (and any MCP client) clean CRUD semantics: `store['ideas.md'] = content`. The total implementation is a thin wrapper — perhaps **300–500 lines of new code** — connecting proven libraries to a clean interface. The biggest open risk is Gemini Gem *knowledge files*, which have no programmatic surface at all; monitor Google's API changelog and the Gems API forum thread for eventual official support, and use Playwright automation as a tactical bridge.