"""Sync a local folder to a Claude Project knowledge base.

Usage:
    python sync_folder.py /path/to/docs PROJECT_UUID [--dry-run] [--session-key SK] [--glob PATTERN]

Examples:
    # Dry run
    python sync_folder.py ./knowledge proj-uuid --dry-run

    # Actual sync
    python sync_folder.py ./knowledge proj-uuid

    # Only .md files
    python sync_folder.py ./knowledge proj-uuid --glob '*.md'
"""

from __future__ import annotations

import fnmatch
import sys


def sync_folder(
    local_dir: str,
    project_id: str,
    *,
    session_key: str | None = None,
    glob_pattern: str | None = None,
    dry_run: bool = False,
    delete_remote_extras: bool = False,
):
    """Sync local files to a Claude Project.

    Returns a dict summarizing what was (or would be) done.
    """
    from aikb import LocalFiles, ClaudeProject

    local = LocalFiles(local_dir, project_id='default')
    remote = ClaudeProject(project_id, session_key=session_key)

    local_files = set(local)
    if glob_pattern:
        local_files = {f for f in local_files if fnmatch.fnmatch(f, glob_pattern)}

    remote_files = set(remote)

    to_add = local_files - remote_files
    to_remove = remote_files - local_files if delete_remote_extras else set()
    common = local_files & remote_files
    to_update = {f for f in common if local[f] != remote[f]}
    unchanged = common - to_update

    summary = {
        'add': sorted(to_add),
        'update': sorted(to_update),
        'remove': sorted(to_remove),
        'unchanged': sorted(unchanged),
    }

    if dry_run:
        print('=== DRY RUN ===')
        for action, files in summary.items():
            if files:
                print(f'\n{action.upper()} ({len(files)}):')
                for f in files:
                    print(f'  {f}')
        if not any(summary[k] for k in ('add', 'update', 'remove')):
            print('\nNothing to do — already in sync.')
        return summary

    for f in to_add | to_update:
        print(f'  {"ADD" if f in to_add else "UPD"} {f}')
        remote[f] = local[f]

    for f in to_remove:
        print(f'  DEL {f}')
        del remote[f]

    total = len(to_add) + len(to_update) + len(to_remove)
    print(f'\nDone: {total} change(s) applied.')
    return summary


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Sync a local folder to a Claude Project knowledge base.'
    )
    parser.add_argument('local_dir', help='Path to local folder')
    parser.add_argument('project_id', help='Claude Project UUID')
    parser.add_argument('--session-key', help='Claude session key')
    parser.add_argument('--glob', dest='glob_pattern', help='Filter files by glob pattern')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change')
    parser.add_argument(
        '--delete-remote-extras',
        action='store_true',
        help='Delete remote files not present locally',
    )
    args = parser.parse_args()

    sync_folder(
        args.local_dir,
        args.project_id,
        session_key=args.session_key,
        glob_pattern=args.glob_pattern,
        dry_run=args.dry_run,
        delete_remote_extras=args.delete_remote_extras,
    )


if __name__ == '__main__':
    main()
