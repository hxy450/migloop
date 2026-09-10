"""CC source discovery, not dispatch or author inference.

The source boundary is the explicit root JSONL plus its sibling
``<root-stem>`` tree. All regular files in that tree are discovered;
links/reparse points are rejected, never followed or silently skipped. Source
paths retain the caller's spelling and the legacy flat traversal order.

Nested workflow journals and unknown JSONLs are auxiliary raw sources, not
agents. A native message envelope establishes a nested actor transcript; no
parent relation is inferred from its directory. Legacy unknown/empty direct
children remain actors, except a positively identified workflow journal.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from typing import Iterable


class CCSourceError(ValueError):
    """The requested source boundary or actor identity is ambiguous/unsafe."""


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _check_entry(path: str, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise CCSourceError(f"CC source link/reparse point is not allowed: {path}")


def _check_ancestors(path: str) -> None:
    current = os.path.abspath(path)
    while True:
        if os.path.lexists(current):
            _check_entry(current, os.lstat(current))
        parent = os.path.dirname(current)
        if parent == current:
            return
        current = parent


def all_source_paths(root: str) -> list[str]:
    """Root first, then every regular attachment in its own tree, sorted.

    This metadata-only function includes logs/scripts/sidecars/unknown files so
    the pool cache key covers them too. A missing root-stem tree means no attachments;
    unreadable directories and links raise instead of pretending completeness.
    """
    root = os.fspath(root)
    _check_ancestors(root)
    boundary = os.path.splitext(root)[0]
    _check_ancestors(boundary)
    if not os.path.exists(boundary):
        return [root]
    if not os.path.isdir(boundary):
        raise CCSourceError(f"CC source boundary is not a directory: {boundary}")
    pending, paths = [boundary], []
    while pending:
        directory = pending.pop()
        # Recheck the directory immediately before reading it. This is not an
        # adversarial filesystem sandbox; callers still need stable snapshots.
        _check_ancestors(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                _check_entry(entry.path, info)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(entry.path)
                else:
                    if not stat.S_ISREG(info.st_mode):
                        raise CCSourceError(f"CC attachment is not a regular file: {entry.path}")
                    paths.append(entry.path)
    # Preserve old Windows flat-source spelling as well as ordering. Discovery
    # now starts one directory higher, so retain the historical /subagents join.
    sub = os.path.join(boundary, "subagents")
    paths = [boundary + "/subagents" + path[len(sub):]
             if path.startswith(sub + os.sep) else path for path in paths]
    return [root, *sorted(paths)]


def _within(path: str, boundary: str) -> bool:
    return os.path.commonpath([_path_key(path), _path_key(boundary)]) == _path_key(boundary)


def subagent_paths(root: str) -> list[str]:
    """Compatibility subset; the collector/cache should reuse all_source_paths."""
    sub = os.path.splitext(os.fspath(root))[0] + "/subagents"
    return [path for path in all_source_paths(root)[1:]
            if path.lower().endswith(".jsonl") and _within(path, sub)]


@dataclass(frozen=True)
class CCRootSources:
    root: str
    subagents: tuple[str, ...]


@dataclass(frozen=True)
class CCSourceSet:
    roots: tuple[str, ...]
    groups: tuple[CCRootSources, ...]
    actor_transcripts: tuple[str, ...]
    auxiliary_sources: tuple[str, ...]
    source_metadata: dict[str, dict[str, str]]


def _is_actor_transcript(path: str, *, direct: bool) -> bool:
    """Inspect record envelopes only; never interpret journal result bodies."""
    _check_ancestors(path)
    before = os.stat(path)
    seen, journal_only = False, True
    try:
        with open(path, encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip():
                    continue
                seen = True
                try:
                    row = json.loads(line)
                except (ValueError, RecursionError):
                    journal_only = False
                    continue
                if not isinstance(row, dict):
                    journal_only = False
                    continue
                message = row.get("message")
                if (isinstance(message, dict) and message.get("role") in ("user", "assistant", "system")
                        and isinstance(message.get("content"), (str, list))):
                    return True
                if not (row.get("type") in ("started", "result") and isinstance(row.get("key"), str)
                        and "message" not in row):
                    journal_only = False
    except UnicodeDecodeError:
        journal_only = False  # Keep original bytes; raw access will disclose its own decode gap.
    finally:
        after = os.stat(path)
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise CCSourceError(f"CC source changed during discovery: {path}")
    return direct and not (seen and journal_only)


def discover(roots: Iterable[str]) -> CCSourceSet:
    """Discover once, partition raw sources, reject ambiguous actor identities.

    Repeated identical root paths are deduplicated; distinct roots sharing a
    legacy sid8 or distinct actor files sharing a stem are rejected before any
    action collection. Identical bodies do not make distinct actors identical.
    """
    normalized_roots: list[str] = []
    root_keys: set[str] = set()
    for raw in roots:
        root = os.fspath(raw)
        key = _path_key(root)
        if key not in root_keys:
            normalized_roots.append(root)
            root_keys.add(key)
    groups, actors, auxiliary = [], [], []
    metadata: dict[str, dict[str, str]] = {}
    identities: dict[str, str] = {}
    source_owners: dict[str, str] = {}

    def own(path: str, root: str) -> None:
        key = _path_key(path)
        if key in source_owners:
            raise CCSourceError(f"ambiguous CC source belongs to multiple roots: {path}; {source_owners[key]}; {root}")
        source_owners[key] = root

    def actor(path: str, identity: str) -> None:
        # Case-folded collision checks are portable across Windows frozen pools.
        key = identity.casefold()
        if key in identities:
            raise CCSourceError(f"ambiguous CC actor id {identity}: {identities[key]}; {path}")
        identities[key] = path
        actors.append(path)

    for root in normalized_roots:
        paths = all_source_paths(root)
        if not stat.S_ISREG(os.stat(root).st_mode):
            raise CCSourceError(f"CC root source is not a regular file: {root}")
        own(root, root)
        actor(root, f"__main__:{os.path.basename(root)[:8]}")
        root_name = os.path.basename(root)
        root_tree = os.path.splitext(root)[0]
        sub_tree = root_tree + "/subagents"
        direct_parent = _path_key(sub_tree)
        metadata[_path_key(root)] = {"logical_name": root_name, "timestamp_policy": "record"}
        subagents = []
        for path in paths[1:]:
            own(path, root)
            is_actor = (path.lower().endswith(".jsonl") and _within(path, sub_tree)
                        and _is_actor_transcript(path, direct=_path_key(os.path.dirname(path)) == direct_parent))
            metadata[_path_key(path)] = {
                "logical_name": root_name + "/" + os.path.relpath(path, root_tree).replace("\\", "/"),
                "timestamp_policy": "record" if is_actor else "unknown",
            }
            if is_actor:
                actor(path, os.path.splitext(os.path.basename(path))[0])
                subagents.append(path)
            else:
                auxiliary.append(path)
        groups.append(CCRootSources(root, tuple(subagents)))
    return CCSourceSet(tuple(normalized_roots), tuple(groups), tuple(actors), tuple(auxiliary), metadata)
