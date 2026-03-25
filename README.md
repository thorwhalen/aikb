
# aikb

Programmatic CRUD for AI project knowledge bases (Claude Projects, Gemini Gems).

Dict-like access to knowledge files — `store['notes.md'] = content` — backed by
local files, Claude Projects (via ClaudeSync), or any custom provider.

To install:	`pip install aikb`

## Quick start

```python
from aikb import LocalKb

store = LocalKb()  # ~/.local/share/aikb/localkb_files/default/
store['ideas.md'] = '# Ideas\nFirst idea'
print(store['ideas.md'])
list(store)          # ['ideas.md']
del store['ideas.md']
```

Every store is a standard Python `MutableMapping` (dict-like), so `len()`,
`in`, `.keys()`, `.values()`, `.items()`, and `.update()` all work.

Override the default directory with a path or the `AIKB_LOCAL_DIR` env var:

```python
store = LocalKb('/path/to/my/knowledge')
store = LocalKb(project_id='research')  # subfolder under default dir
```

## Claude Projects

Manage knowledge files in Claude.ai Projects programmatically:

```bash
pip install aikb[claude]
```

### Browse all your projects

```python
from aikb import ClaudeProjects

projects = ClaudeProjects()
list(projects)                  # ['My Project', 'Another Project', ...]
files = projects['My Project']  # returns a dict-like store
list(files)                     # ['context.md', 'notes.md']
print(files['context.md'])
```

### Direct access by project UUID

```python
from aikb import ClaudeProject

store = ClaudeProject('your-project-uuid')
store['context.md'] = '# Project context\n...'
print(store['context.md'])
del store['context.md']
```

### Getting your session key

aikb automatically looks for a Claude session key in this order:

1. Explicit `session_key` parameter
2. `CLAUDE_SESSION_KEY` environment variable
3. ClaudeSync stored credentials (`~/.claudesync/`)
4. Browser cookies (requires `pip install aikb[cookies]`)

If none are found, you'll get a helpful error with instructions.

**To get your session key manually:**

1. Open https://claude.ai and log in
2. Open Developer Tools (F12) → Application → Cookies
3. Copy the value of the `sessionKey` cookie (starts with `sk-ant-`)
4. Set it:

```bash
export CLAUDE_SESSION_KEY='sk-ant-sid01-...'
```

Or use [ClaudeSync](https://github.com/jahwag/ClaudeSync) to store credentials:

```bash
pip install claudesync
claudesync auth login
```

## Syncing stores

aikb includes a sync engine that works with any two `MutableMapping` stores — plain dicts, `LocalKb`, `ClaudeProject`, or any custom store.

### Push / Pull (one-directional)

```python
from aikb import LocalKb, ClaudeProject, push, pull

local = LocalKb('/path/to/docs')
remote = ClaudeProject('project-uuid')

push(local, remote)                # local → remote (source wins)
push(local, remote, delete=True)   # also remove remote files not in local
pull(local, remote)                # remote → local
```

### Bidirectional sync (three-way reconciliation)

```python
from aikb import sync, clone

# First time: clone to establish a manifest (baseline)
clone(local, remote, manifest_path='.aikb/manifest.json')

# Later: bidirectional sync detects who changed what
sync(local, remote, manifest_path='.aikb/manifest.json')
```

### Status (dry run)

```python
from aikb import status

for action in status(local, remote):
    print(f"{action.action.value:8s} {action.direction:10s} {action.filename}")
```

### Conflict resolution

```python
from aikb import sync, ConflictPolicy

sync(a, b, manifest=m, on_conflict=ConflictPolicy.A_WINS)   # local wins
sync(a, b, manifest=m, on_conflict=ConflictPolicy.SKIP)     # skip conflicts
sync(a, b, manifest=m, on_conflict=my_resolver_function)    # custom callable
```

Works with plain dicts too — no aikb stores required:

```python
from aikb import push
src = {"readme.md": "# Hello", "notes.md": "..."}
tgt = {}
push(src, tgt)  # tgt is now a copy of src
```

## Custom providers

Implement the `KnowledgeBaseProvider` protocol to add new backends:

```python
from aikb import KnowledgeFiles, KnowledgeBaseProvider

class MyProvider:  # no inheritance needed — just implement the methods
    def list_files(self, project_id: str): ...
    def read_file(self, project_id: str, filename: str) -> str: ...
    def upsert_file(self, project_id: str, filename: str, content: str): ...
    def delete_file(self, project_id: str, filename: str): ...

store = KnowledgeFiles(MyProvider(), project_id='my-project')
```

## MCP server

Expose knowledge base CRUD as MCP tools for Claude Desktop, Claude Code, or
any MCP-compatible client:

```bash
pip install aikb[mcp]
python -m aikb.mcp_server
```

Tools exposed: `list_files`, `read_file`, `write_file`, `delete_file` — each
taking `platform` (`"local"` or `"claude"`), `project`, and file parameters.

## dol compatibility

`aikb` stores implement `collections.abc.MutableMapping`, making them natively
compatible with [dol](https://github.com/i2mint/dol):

```bash
pip install aikb[dol]
```

```python
from dol import wrap_kvs
from aikb import LocalKb

store = wrap_kvs(
    LocalKb('/tmp/kb'),
    obj_of_data=lambda s: s.upper(),  # transforms on read
)
```

## Optional dependencies

| Extra | Install | Provides |
|-------|---------|----------|
| `claude` | `pip install aikb[claude]` | Claude Projects via ClaudeSync |
| `cookies` | `pip install aikb[cookies]` | Auto-extract session keys from browser |
| `mcp` | `pip install aikb[mcp]` | FastMCP server |
| `dol` | `pip install aikb[dol]` | dol store transforms |
| `all` | `pip install aikb[all]` | Everything |
