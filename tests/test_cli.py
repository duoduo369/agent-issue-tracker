import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from feishu_issue_tracker.cli import main
from feishu_issue_tracker.push_service import PushPreview
from feishu_issue_tracker.pull_service import PullConfirmationRequired, PullExecutionResult, PullPreview


@dataclass
class _FakeBackend:
    backend_name: str = "feishu"


class CliTests(unittest.TestCase):
    def test_push_reports_missing_config_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            stdout = StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with redirect_stdout(stdout):
                    exit_code = main(["push", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 2)
            payload = stdout.getvalue()
            self.assertIn(".env.example", payload)
            self.assertIn('"user_config_path"', payload)
            self.assertIn("AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN", payload)

    def test_push_preview_does_not_run_doctor_before_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PushPreview(
                backend_name="feishu",
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                tracker_root_locator="root-folder",
                tracker_repo_locator="root-folder/remote-repo",
                tracker_feature_locator="root-folder/remote-repo/feature-a",
                canonical_files=["spec.md"],
                will_create=["spec.md"],
                will_overwrite=[],
                unchanged=[],
                remote_only_canonical=[],
                remote_extra_files=[],
                local_extra_files=[],
                confirmation_required=False,
            )
            try:
                os.chdir(repo_root)
                with (
                    patch("feishu_issue_tracker.cli.resolve_backend", return_value=_FakeBackend()),
                    patch("feishu_issue_tracker.cli.PushService") as push_service_cls,
                    redirect_stdout(stdout),
                ):
                    push_service_cls.return_value.preview_push.return_value = preview
                    exit_code = main(["push", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0)
            payload = stdout.getvalue()
            self.assertIn('"mode": "preview"', payload)
            self.assertIn('"backend": "feishu"', payload)

    def test_pull_returns_structured_execution_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PullPreview(
                backend_name="feishu",
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                tracker_root_locator="root-folder",
                tracker_repo_locator="root-folder/remote-repo",
                tracker_feature_locator="root-folder/remote-repo/feature-a",
                canonical_files=["spec.md"],
                will_create=["spec.md"],
                will_overwrite=[],
                unchanged=[],
                local_only_canonical=[],
                remote_extra_files=[],
                local_extra_files=[],
                confirmation_required=False,
            )
            try:
                os.chdir(repo_root)
                with (
                    patch("feishu_issue_tracker.cli.resolve_backend", return_value=_FakeBackend()),
                    patch("feishu_issue_tracker.cli.PullService") as pull_service_cls,
                    redirect_stdout(stdout),
                ):
                    pull_service_cls.return_value.execute_pull.return_value = PullExecutionResult(
                        preview=preview,
                        pull_result={"summary": {"downloaded": 1}},
                    )
                    exit_code = main(["pull", "--feature", "feature-a", "--confirm"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0)
            payload = stdout.getvalue()
            self.assertIn('"mode": "execute"', payload)
            self.assertIn('"pull_result"', payload)
            self.assertIn('"feature_name": "feature-a"', payload)
            self.assertIn('"backend": "feishu"', payload)

    def test_pull_returns_structured_preview_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PullPreview(
                backend_name="feishu",
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                tracker_root_locator="root-folder",
                tracker_repo_locator="root-folder/remote-repo",
                tracker_feature_locator="root-folder/remote-repo/feature-a",
                canonical_files=["spec.md"],
                will_create=["spec.md"],
                will_overwrite=[],
                unchanged=[],
                local_only_canonical=[],
                remote_extra_files=[],
                local_extra_files=[],
                confirmation_required=False,
            )
            try:
                os.chdir(repo_root)
                with (
                    patch("feishu_issue_tracker.cli.resolve_backend", return_value=_FakeBackend()),
                    patch("feishu_issue_tracker.cli.PullService") as pull_service_cls,
                    redirect_stdout(stdout),
                ):
                    pull_service_cls.return_value.preview_pull.return_value = preview
                    exit_code = main(["pull", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0)
            payload = stdout.getvalue()
            self.assertIn('"mode": "preview"', payload)
            self.assertIn('"preview"', payload)
            self.assertIn('"feature_name": "feature-a"', payload)

    def test_pull_confirmation_required_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PullPreview(
                backend_name="feishu",
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                tracker_root_locator="root-folder",
                tracker_repo_locator="root-folder/remote-repo",
                tracker_feature_locator="root-folder/remote-repo/feature-a",
                canonical_files=["spec.md"],
                will_create=["spec.md"],
                will_overwrite=["spec.md"],
                unchanged=[],
                local_only_canonical=["map.md"],
                remote_extra_files=[],
                local_extra_files=[],
                confirmation_required=True,
            )
            try:
                os.chdir(repo_root)
                with (
                    patch("feishu_issue_tracker.cli.resolve_backend", return_value=_FakeBackend()),
                    patch("feishu_issue_tracker.cli.PullService") as pull_service_cls,
                    redirect_stdout(stdout),
                ):
                    pull_service_cls.return_value.execute_pull.side_effect = PullConfirmationRequired(
                        preview
                    )
                    exit_code = main(["pull", "--feature", "feature-a", "--confirm"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 3)
            payload = stdout.getvalue()
            self.assertIn('"error": "confirmation_required"', payload)
            self.assertIn('"preview"', payload)

    def test_reports_not_implemented_backend_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "AGENT_ISSUE_TRACKER_BACKEND=git\n"
                "AGENT_ISSUE_TRACKER_GIT_REPO_PATH=D:/tracker\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with redirect_stdout(stdout):
                    exit_code = main(["push", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 1)
            payload = stdout.getvalue()
            self.assertIn('"backend": "git"', payload)
            self.assertIn("not implemented", payload.lower())
