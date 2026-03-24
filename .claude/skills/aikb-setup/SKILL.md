---
name: aikb-setup
description: "Use when helping a user install, configure, or start using aikb. Covers installation, authentication setup, first-use walkthroughs, and troubleshooting."
---

# aikb: Setup and Usage Guide

Use this skill when helping someone install aikb, configure authentication, or get started with their first knowledge base operations.

## Installation

### Basic (local files only, zero extra deps)

```bash
pip install aikb
```

### With Claude Projects support

```bash
pip install aikb[claude]
```

### With MCP server

```bash
pip install aikb[mcp]
```

### Everything

```bash
pip install aikb[all]
```

## First use: Local files

The fastest way to try aikb — no configuration needed:

```python
from aikb import LocalFiles

store = LocalFiles('/path/to/knowledge_base')

# Write files
store['context.md'] = '# Project Context\nThis project does...'
store['api-notes.md'] = '# API Notes\nEndpoint documentation...'

# List files
print(list(store))  # ['api-notes.md', 'context.md']

# Read a file
print(store['context.md'])

# Delete a file
del store['api-notes.md']
```

Files are stored as UTF-8 text in `{rootdir}/{project_id}/`. The default `project_id` is `'default'`.

## Setting up Claude Projects access

### Step 1: Get your session key

1. Open https://claude.ai in your browser
2. Open Developer Tools (F12) → Application → Cookies
3. Copy the value of the `sessionKey` cookie (starts with `sk-ant-`)

### Step 2: Configure authentication

**Option A — Environment variable (recommended):**

```bash
export CLAUDE_SESSION_KEY='sk-ant-sid01-...'
```

Then in Python:

```python
from aikb import ClaudeProject
store = ClaudeProject('your-project-uuid')
```

**Option B — Explicit parameter:**

```python
store = ClaudeProject('your-project-uuid', session_key='sk-ant-sid01-...')
```

**Option C — ClaudeSync config:**

If you've already configured ClaudeSync (`claudesync auth login`), aikb will use its stored credentials automatically.

### Step 3: Find your project UUID

Project UUIDs are visible in the Claude.ai URL when you open a project:
`https://claude.ai/project/{project-uuid}`

## Setting up the MCP server

### For Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aikb": {
      "command": "python",
      "args": ["-m", "aikb.mcp_server"]
    }
  }
}
```

### For Claude Code

```bash
claude mcp add aikb -- python -m aikb.mcp_server
```

### Standalone

```bash
python -m aikb.mcp_server
```

## Multi-project setup

```python
from aikb import LocalFiles, ClaudeProject, KnowledgeMall

mall = KnowledgeMall(
    local=LocalFiles('/tmp/kb'),
    project_a=ClaudeProject('uuid-a'),
    project_b=ClaudeProject('uuid-b'),
)

# Access by name
list(mall['local'])
mall['project_a']['file.md'] = 'content'
```

## Troubleshooting

### `ImportError: 'claudesync' is required`

Install the Claude extras: `pip install aikb[claude]`

### `ImportError: 'fastmcp' is required`

Install the MCP extras: `pip install aikb[mcp]`

### `KeyError` when reading a file

The file doesn't exist in the project. Use `list(store)` to see available files, or `'filename' in store` to check.

### Session key expired (403 errors)

Claude.ai session keys expire periodically. Get a fresh one from your browser cookies and update `CLAUDE_SESSION_KEY`.

### `ConnectionError` / `429` rate limiting

ClaudeSync communicates with Claude.ai's internal API. Retry after a few seconds. Avoid rapid bulk operations.
