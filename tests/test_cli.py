import os
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from feishu_issue_tracker.cli import main
from feishu_issue_tracker.feishu_cli import LarkCliDoctorResult
from feishu_issue_tracker.pull_service import PullConfirmationRequired, PullExecutionResult, PullPreview


@dataclass
class _FakeFeishuClient:
    doctor_result: LarkCliDoctorResult

    def doctor(self) -> LarkCliDoctorResult:
        return self.doctor_result

    def preferred_access_strategy(self) -> str:
        return "bot_first"

    def user_fallback_scopes(self) -> list[str]:
        return [
            "space:document:retrieve",
            "space:folder:create",
            "drive:drive.metadata:readonly",
            "drive:file:upload",
            "drive:file:download",
        ]


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
            self.assertIn(".env.example", stdout.getvalue())

    def test_doctor_reports_config_and_lark_cli_state(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            stdout = StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with (
                    patch(
                        "feishu_issue_tracker.cli.LarkCliFeishuClient",
                        return_value=_FakeFeishuClient(
                            LarkCliDoctorResult(
                                installed=True,
                                executable="lark-cli.cmd",
                                ready=False,
                                status="not_configured",
                                hint="run `lark-cli config init --new`",
                                recommended_command="lark-cli config init --new",
                            )
                        ),
                    ),
                    redirect_stdout(stdout),
                ):
                    exit_code = main(["doctor"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 1)
            payload = stdout.getvalue()
            self.assertIn('"mode": "doctor"', payload)
            self.assertIn('"preferred": "bot_first"', payload)
            self.assertIn('"fallback": "user_fallback"', payload)
            self.assertIn('"missing_keys"', payload)
            self.assertIn('"status": "not_configured"', payload)

    def test_push_returns_structured_lark_cli_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with (
                    patch(
                        "feishu_issue_tracker.cli.LarkCliFeishuClient",
                        return_value=_FakeFeishuClient(
                            LarkCliDoctorResult(
                                installed=True,
                                executable="lark-cli.cmd",
                                ready=False,
                                status="not_configured",
                                hint="run `lark-cli config init --new`",
                                recommended_command="lark-cli config init --new",
                            )
                        ),
                    ),
                    redirect_stdout(stdout),
                ):
                    exit_code = main(["push", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 4)
            payload = stdout.getvalue()
            self.assertIn('"error": "not_configured"', payload)
            self.assertIn('"recommended_command": "lark-cli config init --new"', payload)

    def test_pull_returns_structured_execution_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PullPreview(
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                remote_root_folder_token="root-folder",
                remote_repo_folder_token="root-folder/remote-repo",
                remote_feature_folder_token="root-folder/remote-repo/feature-a",
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
                    patch(
                        "feishu_issue_tracker.cli.LarkCliFeishuClient",
                        return_value=_FakeFeishuClient(
                            LarkCliDoctorResult(
                                installed=True,
                                executable="lark-cli.cmd",
                                ready=True,
                                status="ready",
                                hint=None,
                                recommended_command=None,
                            )
                        ),
                    ),
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

    def test_pull_returns_structured_preview_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            (repo_root / ".env").write_text(
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PullPreview(
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                remote_root_folder_token="root-folder",
                remote_repo_folder_token="root-folder/remote-repo",
                remote_feature_folder_token="root-folder/remote-repo/feature-a",
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
                    patch(
                        "feishu_issue_tracker.cli.LarkCliFeishuClient",
                        return_value=_FakeFeishuClient(
                            LarkCliDoctorResult(
                                installed=True,
                                executable="lark-cli.cmd",
                                ready=True,
                                status="ready",
                                hint=None,
                                recommended_command=None,
                            )
                        ),
                    ),
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
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN=root-folder\n",
                encoding="utf-8",
            )
            stdout = StringIO()
            original_cwd = Path.cwd()
            preview = PullPreview(
                feature_name="feature-a",
                resolved_repo_name="remote-repo",
                remote_root_folder_token="root-folder",
                remote_repo_folder_token="root-folder/remote-repo",
                remote_feature_folder_token="root-folder/remote-repo/feature-a",
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
                    patch(
                        "feishu_issue_tracker.cli.LarkCliFeishuClient",
                        return_value=_FakeFeishuClient(
                            LarkCliDoctorResult(
                                installed=True,
                                executable="lark-cli.cmd",
                                ready=True,
                                status="ready",
                                hint=None,
                                recommended_command=None,
                            )
                        ),
                    ),
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
