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

### With auto session key extraction from browser

```bash
pip install aikb[cookies]
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
from aikb import LocalKb

store = LocalKb()  # uses ~/.local/share/aikb/localkb_files/default/

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

Override the default directory:

```python
store = LocalKb('/custom/path')               # explicit directory
store = LocalKb(project_id='research')         # subfolder under default dir
```

Or set `AIKB_LOCAL_DIR` environment variable to change the default root.

## Setting up Claude Projects access

### Session key auto-discovery

aikb automatically looks for a session key in this order:
1. Explicit `session_key` parameter
2. `CLAUDE_SESSION_KEY` environment variable
3. ClaudeSync stored credentials (`~/.claudesync/`)
4. Browser cookies (requires `pip install aikb[cookies]`)

If none found, a `RuntimeError` is raised with step-by-step instructions.

### Manual session key extraction

1. Open https://claude.ai in your browser
2. Open Developer Tools (F12) → Application → Cookies
3. Copy the value of the `sessionKey` cookie (starts with `sk-ant-`)

Then:

```bash
export CLAUDE_SESSION_KEY='sk-ant-sid01-...'
```

### Using ClaudeSync credentials

If you've already configured ClaudeSync:

```bash
pip install claudesync
claudesync auth login
```

aikb will use its stored credentials automatically.

### Browse projects

```python
from aikb import ClaudeProjects

projects = ClaudeProjects()
list(projects)                    # ['My Project', 'Research', ...]
files = projects['My Project']    # dict-like access to knowledge files
list(files)                       # ['context.md', 'notes.md']
```

### Direct project access

```python
from aikb import ClaudeProject

store = ClaudeProject('project-uuid', session_key='sk-ant-...')
```

Project UUIDs are visible in the Claude.ai URL: `https://claude.ai/project/{uuid}`

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

## Troubleshooting

### `ImportError: 'claudesync' is required`

Install the Claude extras: `pip install aikb[claude]`

### `ImportError: 'fastmcp' is required`

Install the MCP extras: `pip install aikb[mcp]`

### `RuntimeError: Could not find a valid Claude session key`

Follow the instructions in the error message. The easiest options:
- Set `CLAUDE_SESSION_KEY` env var
- Install `aikb[cookies]` for auto browser extraction
- Run `claudesync auth login`

### `KeyError` when reading a file

The file doesn't exist in the project. Use `list(store)` to see available files.

### Session key expired (403 errors)

Claude.ai session keys expire periodically. Get a fresh one from your browser cookies.

### Multiple organizations

If you belong to multiple Claude organizations, specify which one:

```python
ClaudeProjects(organization_id='org-uuid')
ClaudeProject('project-uuid', organization_id='org-uuid')
```
