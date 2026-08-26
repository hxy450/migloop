"""Common source-adapter contract used by the CLI.

An adapter owns only source-specific concerns: recognizing a transcript,
discovering sessions, and normalizing one session into MigLoop's trace dict.
Rendering, comparison, chat, and lineage presentation consume that common
trace and must not branch on the source format.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SessionCandidate:
    mtime: float
    path: str
    project: str
    size: int
    format: str
    session_id: str


class SourceAdapter(Protocol):
    FORMAT: str
    SUPPORTS_LIVE: bool

    def default_root(self) -> str: ...

    def is_session(self, path: str) -> bool: ...

    def iter_sessions(self, root: str) -> Iterable[SessionCandidate]: ...

    def extract(self, path: str) -> dict[str, Any]: ...

