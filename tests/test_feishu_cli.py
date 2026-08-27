import json
import unittest
from pathlib import Path
from unittest.mock import patch

from feishu_issue_tracker.feishu_cli import (
    LarkCliDoctorResult,
    LarkCliFeishuClient,
    LarkCliNotInstalledError,
    USER_FALLBACK_SCOPES,
)


class _CompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class LarkCliFeishuClientTests(unittest.TestCase):
    def test_ensure_ready_uses_resolved_cli_path(self) -> None:
        client = LarkCliFeishuClient()
        resolved_path = r"C:\Users\duodu\AppData\Roaming\npm\lark-cli.CMD"

        with (
            patch("feishu_issue_tracker.feishu_cli.shutil.which", return_value=resolved_path),
            patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock,
        ):
            run_mock.return_value = _CompletedProcess(0, stdout='{"ok": true}')

            client.ensure_ready()

        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0][0], resolved_path)
        self.assertEqual(run_mock.call_args.args[0][1:], ["auth", "status", "--json"])

    def test_ensure_ready_raises_when_cli_missing(self) -> None:
        client = LarkCliFeishuClient()

        with patch("feishu_issue_tracker.feishu_cli.shutil.which", return_value=None):
            with self.assertRaises(LarkCliNotInstalledError):
                client.ensure_ready()

    def test_run_json_decodes_utf8_bytes(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.return_value = _CompletedProcess(0, stdout='{"ok": true}'.encode("utf-8"))

            payload = client._run_json(["auth", "status", "--json"], cwd=None)

        self.assertEqual(payload, {"ok": True})

    def test_doctor_reports_not_configured_with_recommended_command(self) -> None:
        client = LarkCliFeishuClient()
        resolved_path = r"C:\Users\duodu\AppData\Roaming\npm\lark-cli.CMD"
        hint = (
            "run `lark-cli config init --new` in the background. "
            "It blocks and outputs a verification URL."
        )

        with (
            patch("feishu_issue_tracker.feishu_cli.shutil.which", return_value=resolved_path),
            patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock,
        ):
            run_mock.return_value = _CompletedProcess(
                1,
                stdout=json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "type": "config",
                            "subtype": "not_configured",
                            "hint": hint,
                        },
                    }
                ),
            )

            result = client.doctor()

        self.assertEqual(
            result,
            LarkCliDoctorResult(
                installed=True,
                executable=resolved_path,
                ready=False,
                status="not_configured",
                hint=hint,
                recommended_command="lark-cli config init --new",
            ),
        )

    def test_run_json_parses_last_json_document_from_mixed_output(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")
        mixed_output = "\n".join(
            [
                "[page 1] fetching...",
                '{"code": 1061004, "msg": "forbidden."}',
                '{"ok": false, "error": {"type": "authorization", "subtype": "permission_denied", "identity": "bot"}}',
            ]
        )

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.return_value = _CompletedProcess(1, stdout=mixed_output)

            result = client._invoke_json(["drive", "files", "list", "--json"], cwd=None)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.payload["error"]["subtype"], "permission_denied")

    def test_run_json_parses_json_across_stdout_and_stderr(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.return_value = _CompletedProcess(
                1,
                stdout='{"code": 1061004, "msg": "forbidden."}',
                stderr='{"ok": false, "error": {"type": "authorization", "subtype": "permission_denied", "identity": "bot"}}',
            )

            result = client._invoke_json(["drive", "files", "list", "--json"], cwd=None)

        self.assertEqual(result.payload["error"]["subtype"], "permission_denied")

    def test_drive_commands_recommend_user_login_when_bot_cannot_access_resource(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.side_effect = [
                _CompletedProcess(
                    1,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "error": {
                                "type": "authorization",
                                "subtype": "permission_denied",
                                "identity": "bot",
                                "message": "bot lacks permission for the requested resource",
                            },
                        }
                    ),
                ),
                _CompletedProcess(
                    0,
                    stdout=json.dumps(
                        {
                            "appId": "cli_app",
                            "identities": {
                                "bot": {"status": "ready", "available": True},
                                "user": {"status": "missing", "available": False},
                            },
                        }
                    ),
                ),
            ]

            result = client._invoke_drive_json(["drive", "files", "list", "--json"], cwd=None)

        self.assertEqual(result.payload["error"]["subtype"], "user_identity_missing")
        self.assertEqual(
            result.payload["error"]["recommended_command"],
            'lark-cli auth login --scope "space:document:retrieve space:folder:create drive:drive.metadata:readonly drive:file:upload drive:file:download" --no-wait --json',
        )

    def test_drive_commands_request_full_fallback_scope_set_when_user_missing_subset(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.side_effect = [
                _CompletedProcess(
                    1,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "error": {
                                "type": "authorization",
                                "subtype": "permission_denied",
                                "identity": "bot",
                                "message": "bot lacks permission for the requested resource",
                            },
                        }
                    ),
                ),
                _CompletedProcess(
                    0,
                    stdout=json.dumps(
                        {
                            "appId": "cli_app",
                            "identities": {
                                "bot": {"status": "ready", "available": True},
                                "user": {
                                    "status": "ready",
                                    "available": True,
                                    "scope": "auth:user.id:read space:document:retrieve offline_access",
                                },
                            },
                        }
                    ),
                ),
            ]

            result = client._invoke_drive_json(["drive", "files", "list", "--json"], cwd=None)

        self.assertEqual(result.payload["error"]["subtype"], "missing_scope")
        self.assertEqual(
            result.payload["error"]["missing_scopes"],
            [
                "space:folder:create",
                "drive:drive.metadata:readonly",
                "drive:file:upload",
                "drive:file:download",
            ],
        )
        self.assertEqual(
            result.payload["error"]["recommended_command"],
            'lark-cli auth login --scope "space:folder:create drive:drive.metadata:readonly drive:file:upload drive:file:download" --no-wait --json',
        )
        self.assertEqual(run_mock.call_count, 2)

    def test_drive_commands_retry_with_user_identity_when_available(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.side_effect = [
                _CompletedProcess(
                    1,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "error": {
                                "type": "authorization",
                                "subtype": "permission_denied",
                                "identity": "bot",
                                "message": "bot lacks permission for the requested resource",
                            },
                        }
                    ),
                ),
                _CompletedProcess(
                    0,
                    stdout=json.dumps(
                        {
                            "appId": "cli_app",
                            "identities": {
                                "bot": {"status": "ready", "available": True},
                                "user": {
                                    "status": "ready",
                                    "available": True,
                                    "scope": " ".join(USER_FALLBACK_SCOPES),
                                },
                            },
                        }
                    ),
                ),
                _CompletedProcess(0, stdout='{"ok": true, "data": {"files": []}}'),
            ]

            result = client._invoke_drive_json(["drive", "files", "list", "--json"], cwd=None)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.payload["ok"], True)
        self.assertEqual(run_mock.call_args_list[-1].args[0][-2:], ["--as", "user"])

    def test_drive_commands_merge_cli_missing_scope_back_into_full_recommendation(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.side_effect = [
                _CompletedProcess(
                    1,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "error": {
                                "type": "authorization",
                                "subtype": "permission_denied",
                                "identity": "bot",
                                "message": "bot lacks permission for the requested resource",
                            },
                        }
                    ),
                ),
                _CompletedProcess(
                    0,
                    stdout=json.dumps(
                        {
                            "appId": "cli_app",
                            "identities": {
                                "bot": {"status": "ready", "available": True},
                                "user": {
                                    "status": "ready",
                                    "available": True,
                                    "scope": " ".join(USER_FALLBACK_SCOPES),
                                },
                            },
                        }
                    ),
                ),
                _CompletedProcess(
                    1,
                    stdout=json.dumps(
                        {
                            "ok": False,
                            "identity": "user",
                            "error": {
                                "type": "authorization",
                                "subtype": "missing_scope",
                                "identity": "user",
                                "missing_scopes": ["space:folder:create"],
                            },
                        }
                    ),
                ),
            ]

            result = client._invoke_drive_json(["drive", "files", "create_folder", "--json"], cwd=None)

        self.assertEqual(result.payload["error"]["subtype"], "missing_scope")
        self.assertEqual(result.payload["error"]["missing_scopes"], ["space:folder:create"])
        self.assertEqual(
            result.payload["error"]["recommended_command"],
            'lark-cli auth login --scope "space:folder:create" --no-wait --json',
        )

    def test_pull_uses_overwrite_policy(self) -> None:
        client = LarkCliFeishuClient(cli_executable="lark-cli.cmd")

        with patch("feishu_issue_tracker.feishu_cli.subprocess.run") as run_mock:
            run_mock.return_value = _CompletedProcess(0, stdout='{"ok": true, "data": {"summary": {}}}')

            client.pull(
                repo_root=Path("D:/repo"),
                local_dir=Path("D:/repo/.scratch/staging"),
                folder_token="folder-token",
            )

        self.assertEqual(
            run_mock.call_args.args[0][1:],
            [
                "drive",
                "+pull",
                "--json",
                "--local-dir",
                ".scratch/staging",
                "--folder-token",
                "folder-token",
                "--if-exists",
                "overwrite",
                "--as",
                "bot",
            ],
        )


if __name__ == "__main__":
    unittest.main()
