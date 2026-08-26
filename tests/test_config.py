import json
import tempfile
import unittest
from pathlib import Path

from feishu_issue_tracker.config import (
    REQUIRED_CONFIG_KEYS,
    UserConfigStore,
    resolve_config,
)


class ResolveConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        (self.repo_root / ".git").mkdir()
        self.user_config_path = self.repo_root / ".tmp-user-config.json"
        self.user_config_store = UserConfigStore(self.user_config_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_prefers_environment_over_repo_env_and_user_config(self) -> None:
        (self.repo_root / ".env").write_text(
            "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=repo-root\n"
            "FEISHU_ISSUE_TRACKER_REPO_NAME=repo-env-name\n",
            encoding="utf-8",
        )
        self.user_config_store.save(
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "user-root",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "user-name",
            }
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "env-root",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "env-name",
            },
            user_config_store=self.user_config_store,
        )

        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "env-root")
        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_REPO_NAME"], "env-name")
        self.assertEqual(result.sources["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "env")

    def test_uses_user_config_when_env_and_repo_env_are_missing(self) -> None:
        self.user_config_store.save(
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "user-root",
            }
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={},
            user_config_store=self.user_config_store,
        )

        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "user-root")
        self.assertEqual(result.sources["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "user")

    def test_reports_missing_required_config(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={},
            user_config_store=self.user_config_store,
        )

        self.assertEqual(result.missing_keys, REQUIRED_CONFIG_KEYS)

    def test_persists_user_config_values(self) -> None:
        self.user_config_store.save(
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "folder-token",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "repo-name",
            }
        )

        self.assertEqual(
            json.loads(self.user_config_path.read_text(encoding="utf-8")),
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "folder-token",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "repo-name",
            },
        )

    def test_save_merges_with_existing_user_config(self) -> None:
        self.user_config_store.save(
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "folder-token",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "repo-name",
            }
        )

        self.user_config_store.save(
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "updated-token",
            }
        )

        self.assertEqual(
            json.loads(self.user_config_path.read_text(encoding="utf-8")),
            {
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "updated-token",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "repo-name",
            },
        )
