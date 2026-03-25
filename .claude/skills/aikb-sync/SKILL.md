---
name: aikb-sync
description: "Use when syncing knowledge files between platforms or directories — e.g., pushing local files to Claude Projects, mirroring between projects, or batch-updating a knowledge base from a folder of markdown files."
---

# aikb: Sync Knowledge Files

Use this skill when syncing, mirroring, or batch-managing knowledge files across platforms or directories.

## Sync patterns

### Push local files to Claude Project

```python
from aikb import LocalKb, ClaudeProject

local = LocalKb('/path/to/docs')
remote = ClaudeProject('project-uuid')

# Push all files
remote.update(local)

# Push specific files
for name in ['context.md', 'api.md']:
    remote[name] = local[name]
```

### Pull from Claude Project to local

```python
local.update(remote)
```

### Mirror between two projects

```python
proj_a = ClaudeProject('uuid-a')
proj_b = ClaudeProject('uuid-b')
proj_b.update(proj_a)
```

### Selective sync with filtering

```python
# Only markdown files
for name in local:
    if name.endswith('.md'):
        remote[name] = local[name]

# Only files that differ
for name in local:
    if name not in remote or remote[name] != local[name]:
        remote[name] = local[name]
```

### Delete remote files not present locally

```python
remote_only = set(remote) - set(local)
for name in remote_only:
    del remote[name]
```

## Helper script: sync_folder.py

The script at `.claude/skills/aikb-sync/scripts/sync_folder.py` provides a
ready-made sync operation:

```bash
# Dry run (show what would change)
python .claude/skills/aikb-sync/scripts/sync_folder.py \
  /path/to/local/docs project-uuid --dry-run

# Actual sync
python .claude/skills/aikb-sync/scripts/sync_folder.py \
  /path/to/local/docs project-uuid

# With explicit session key
python .claude/skills/aikb-sync/scripts/sync_folder.py \
  /path/to/local/docs project-uuid --session-key 'sk-ant-...'

# Only .md files
python .claude/skills/aikb-sync/scripts/sync_folder.py \
  /path/to/local/docs project-uuid --glob '*.md'
```

## Workflow: Keep Claude Project in sync with a repo folder

```python
from aikb import LocalKb, ClaudeProject

local = LocalKb('knowledge')
remote = ClaudeProject('project-uuid')

# Full bidirectional diff
local_files = set(local)
remote_files = set(remote)

added = local_files - remote_files
removed = remote_files - local_files
common = local_files & remote_files
changed = {f for f in common if local[f] != remote[f]}

print(f"To add: {added}")
print(f"To remove: {removed}")
print(f"Changed: {changed}")

# Apply
for f in added | changed:
    remote[f] = local[f]
for f in removed:
    del remote[f]
```

## Using ClaudeProjects for discovery

```python
from aikb import ClaudeProjects

projects = ClaudeProjects()
for name in projects:
    files = projects[name]
    print(f"{name}: {list(files)}")
```
