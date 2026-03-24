
# aikb

Programmatic CRUD for AI project knowledge bases (Claude Projects, Gemini Gems).

Dict-like access to knowledge files — `store['notes.md'] = content` — backed by
local files, Claude Projects (via ClaudeSync), or any custom provider.

To install:	`pip install aikb`

## Quick start

```python
from aikb import LocalFiles

store = LocalFiles('/tmp/my_kb')
store['ideas.md'] = '# Ideas\nFirst idea'
print(store['ideas.md'])
list(store)          # ['ideas.md']
del store['ideas.md']
```

Every store is a standard Python `MutableMapping` (dict-like), so `len()`,
`in`, `.keys()`, `.values()`, `.items()`, and `.update()` all work.

## Claude Projects

Manage knowledge files in Claude.ai Projects programmatically:

```bash
pip install aikb[claude]
```

```python
from aikb import ClaudeProject

store = ClaudeProject('your-project-uuid', session_key='sk-ant-...')

# List existing files
list(store)

# Add or update a file
store['context.md'] = '# Project context\n...'

# Read a file
print(store['context.md'])

# Delete a file
del store['context.md']
```

Authentication priority:
1. Explicit `session_key` parameter
2. `CLAUDE_SESSION_KEY` environment variable
3. ClaudeSync's stored config

## Multi-project workflows (Mall)

Use `KnowledgeMall` to manage multiple projects or platforms at once:

```python
from aikb import LocalFiles, ClaudeProject, KnowledgeMall

mall = KnowledgeMall(
    staging=LocalFiles('/tmp/staging'),
    prod=ClaudeProject('project-uuid', session_key='sk-ant-...'),
)

# Draft locally, then push to Claude
mall['staging']['notes.md'] = '# Notes\nDraft content'
mall['prod']['notes.md'] = mall['staging']['notes.md']
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
from aikb import LocalFiles

store = wrap_kvs(
    LocalFiles('/tmp/kb'),
    obj_of_data=lambda s: s.upper(),  # transforms on read
)
```

## Optional dependencies

| Extra | Install | Provides |
|-------|---------|----------|
| `claude` | `pip install aikb[claude]` | Claude Projects via ClaudeSync |
| `mcp` | `pip install aikb[mcp]` | FastMCP server |
| `dol` | `pip install aikb[dol]` | dol store transforms |
| `all` | `pip install aikb[all]` | Everything |
