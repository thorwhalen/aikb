"""Programmatic CRUD for AI project knowledge bases (Claude Projects, Gemini Gems)."""

from aikb.base import (
    KnowledgeFiles,
    KnowledgeBaseProvider,
    LocalFilesProvider,
    ClaudeProjectsProvider,
    ClaudeProjects,
    LocalKb,
    ClaudeProject,
)
from aikb.sync import (
    status,
    push,
    pull,
    sync,
    clone,
    snapshot,
    reconcile,
    content_hash,
    SyncAction,
    ActionType,
    ConflictPolicy,
    SyncConflictError,
)
