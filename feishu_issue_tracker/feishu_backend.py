from __future__ import annotations

from pathlib import Path

from feishu_issue_tracker.backend import SyncStatus
from feishu_issue_tracker.config import FEISHU_ROOT_FOLDER_TOKEN_KEY, ResolvedConfig
from feishu_issue_tracker.feishu_cli import LarkCliFeishuClient


class FeishuPersistenceBackend:
    backend_name = "feishu"

    def __init__(self, client: LarkCliFeishuClient | None = None) -> None:
        self.client = client or LarkCliFeishuClient()

    def ensure_ready(self) -> None:
        self.client.ensure_ready()

    def root_locator_from_config(self, *, resolved_config: ResolvedConfig) -> str:
        return resolved_config.values[FEISHU_ROOT_FOLDER_TOKEN_KEY]

    def find_remote_repo(self, *, root_locator: str, repo_name: str) -> str | None:
        return self.client.find_child_folder(root_locator, repo_name)

    def find_remote_feature(self, *, repo_locator: str, feature_name: str) -> str | None:
        return self.client.find_child_folder(repo_locator, feature_name)

    def create_remote_repo(self, *, root_locator: str, repo_name: str) -> str:
        return self.client.create_folder(root_locator, repo_name)

    def create_remote_feature(self, *, repo_locator: str, feature_name: str) -> str:
        return self.client.create_folder(repo_locator, feature_name)

    def delete_remote_paths(self, *, remote_locator: str, rel_paths: list[str]) -> None:
        return None

    def status(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> SyncStatus:
        return self.client.status(repo_root=repo_root, local_dir=local_dir, folder_token=remote_locator)

    def push(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> dict:
        return self.client.push(repo_root=repo_root, local_dir=local_dir, folder_token=remote_locator)

    def pull(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> dict:
        return self.client.pull(repo_root=repo_root, local_dir=local_dir, folder_token=remote_locator)
