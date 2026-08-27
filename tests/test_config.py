import tempfile
import unittest
from pathlib import Path

from feishu_issue_tracker.config import (
    BACKEND_KEY,
    FEISHU_ROOT_FOLDER_TOKEN_KEY,
    GIT_BRANCH_KEY,
    GIT_REPO_PATH_KEY,
    REPO_NAME_KEY,
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
            "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=repo-root\n"
            "AGENT_ISSUE_TRACKER_REPO_NAME=repo-env-name\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={
                BACKEND_KEY: "feishu",
                FEISHU_ROOT_FOLDER_TOKEN_KEY: "env-root",
                REPO_NAME_KEY: "env-name",
            },
        )

        self.assertEqual(result.values[FEISHU_ROOT_FOLDER_TOKEN_KEY], "env-root")
        self.assertEqual(result.values[REPO_NAME_KEY], "env-name")
        self.assertEqual(result.sources[FEISHU_ROOT_FOLDER_TOKEN_KEY], "env")

    def test_uses_repo_env_when_env_is_missing(self) -> None:
        (self.repo_root / ".env").write_text(
            "AGENT_ISSUE_TRACKER_BACKEND=feishu\n"
            "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=repo-root\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={},
        )

        self.assertEqual(result.values[FEISHU_ROOT_FOLDER_TOKEN_KEY], "repo-root")
        self.assertEqual(result.sources[FEISHU_ROOT_FOLDER_TOKEN_KEY], "repo_env")

    def test_reports_missing_required_config(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={},
        )

        self.assertEqual(result.missing_keys, REQUIRED_CONFIG_KEYS)
        self.assertEqual(result.backend, "")

    def test_uses_user_level_config_when_env_and_repo_env_are_missing(self) -> None:
        user_config_path = self.repo_root / "user-config.env"
        user_config_path.write_text(
            "AGENT_ISSUE_TRACKER_BACKEND=feishu\n"
            "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=user-root\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={},
            user_config_path=user_config_path,
        )

        self.assertEqual(result.values[FEISHU_ROOT_FOLDER_TOKEN_KEY], "user-root")
        self.assertEqual(result.sources[FEISHU_ROOT_FOLDER_TOKEN_KEY], "user_env")
        self.assertEqual(result.user_config_path, user_config_path)

    def test_accepts_legacy_feishu_keys_as_aliases(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={
                BACKEND_KEY: "feishu",
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "legacy-root",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "legacy-repo",
            },
        )

        self.assertEqual(result.values[FEISHU_ROOT_FOLDER_TOKEN_KEY], "legacy-root")
        self.assertEqual(result.values[REPO_NAME_KEY], "legacy-repo")

    def test_switches_required_keys_with_selected_backend(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={BACKEND_KEY: "git"},
        )

        self.assertEqual(result.backend, "git")
        self.assertEqual(result.missing_keys, [GIT_REPO_PATH_KEY])

    def test_requires_backend_even_when_other_values_exist(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={FEISHU_ROOT_FOLDER_TOKEN_KEY: "repo-root"},
        )

        self.assertEqual(result.missing_keys, [BACKEND_KEY])

    def test_reads_optional_git_branch_config(self) -> None:
        result = resolve_config(
            repo_root=self.repo_root,
            env={
                BACKEND_KEY: "git",
                GIT_REPO_PATH_KEY: "D:/tracker",
                GIT_BRANCH_KEY: "issue-sync",
            },
        )

        self.assertEqual(result.backend, "git")
        self.assertEqual(result.values[GIT_BRANCH_KEY], "issue-sync")

    def test_reads_legacy_user_config_path_for_back_compat(self) -> None:
        appdata_root = self.repo_root / "appdata"
        legacy_config_path = appdata_root / "feishu-issue-tracker" / "config.env"
        legacy_config_path.parent.mkdir(parents=True)
        legacy_config_path.write_text(
            "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=legacy-user-root\n",
            encoding="utf-8",
        )

        result = resolve_config(
            repo_root=self.repo_root,
            env={
                "APPDATA": str(appdata_root),
                BACKEND_KEY: "feishu",
            },
        )

        self.assertEqual(result.values[FEISHU_ROOT_FOLDER_TOKEN_KEY], "legacy-user-root")
        self.assertEqual(result.sources[FEISHU_ROOT_FOLDER_TOKEN_KEY], "user_env")
