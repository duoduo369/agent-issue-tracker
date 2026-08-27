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
