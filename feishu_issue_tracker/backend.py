from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from feishu_issue_tracker.config import ResolvedConfig


class PersistenceBackendError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: str = "command_error",
        hint: str | None = None,
        recommended_command: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.hint = hint
        self.recommended_command = recommended_command


@dataclass(frozen=True)
class SyncStatus:
    local_only: list[str]
    modified: list[str]
    unchanged: list[str]
    remote_only: list[str]


class PersistenceBackend(Protocol):
    backend_name: str

    def ensure_ready(self) -> None: ...

    def prepare_pull_preview(self) -> None: ...

    def root_locator_from_config(self, *, resolved_config: ResolvedConfig) -> str: ...

    def find_remote_repo(self, *, root_locator: str, repo_name: str) -> str | None: ...

    def find_remote_feature(self, *, repo_locator: str, feature_name: str) -> str | None: ...

    def create_remote_repo(self, *, root_locator: str, repo_name: str) -> str: ...

    def create_remote_feature(self, *, repo_locator: str, feature_name: str) -> str: ...

    def delete_remote_paths(self, *, remote_locator: str, rel_paths: list[str]) -> int: ...

    def status(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> SyncStatus: ...

    def push(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> dict: ...

    def pull(
        self,
        *,
        repo_root: Path,
        local_dir: Path,
        remote_locator: str,
        refresh: bool = True,
    ) -> dict: ...
