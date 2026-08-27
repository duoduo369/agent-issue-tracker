import tempfile
import unittest
from pathlib import Path

from feishu_issue_tracker.config import (
    REQUIRED_CONFIG_KEYS,
    resolve_config,
)


class ResolveConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        (self.repo_root / ".git").mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_prefers_environment_over_repo_env(self) -> None:
        (self.repo_root / ".env").write_text(
            "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=repo-root\n"
            "FEISHU_ISSUE_TRACKER_REPO_NAME=repo-env-name\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "env-root",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "env-name",
            },
        )

        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "env-root")
        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_REPO_NAME"], "env-name")
        self.assertEqual(result.sources["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "env")

    def test_uses_repo_env_when_env_is_missing(self) -> None:
        (self.repo_root / ".env").write_text(
            "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=repo-root\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={},
        )

        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "repo-root")
        self.assertEqual(result.sources["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "repo_env")

    def test_reports_missing_required_config(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={},
        )

        self.assertEqual(result.missing_keys, REQUIRED_CONFIG_KEYS)

    def test_uses_user_level_config_when_env_and_repo_env_are_missing(self) -> None:
        user_config_path = self.repo_root / "user-config.env"
        user_config_path.write_text(
            "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=user-root\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={},
            user_config_path=user_config_path,
        )

        self.assertEqual(result.values["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "user-root")
        self.assertEqual(result.sources["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"], "user_env")
        self.assertEqual(result.user_config_path, user_config_path)
