from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

USER_FALLBACK_SCOPES = (
    "space:document:retrieve",
    "space:folder:create",
    "drive:drive.metadata:readonly",
    "drive:file:upload",
    "drive:file:download",
)


class LarkCliError(RuntimeError):
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


class LarkCliNotInstalledError(LarkCliError):
    pass


class LarkCliAuthError(LarkCliError):
    pass


class RemoteFolderConflictError(LarkCliError):
    pass


@dataclass(frozen=True)
class DriveDiffStatus:
    local_only: list[str]
    modified: list[str]
    unchanged: list[str]
    remote_only: list[str]


@dataclass(frozen=True)
class LarkCliDoctorResult:
    installed: bool
    executable: str | None
    ready: bool
    status: str
    hint: str | None
    recommended_command: str | None


@dataclass(frozen=True)
class _JsonCommandResult:
    returncode: int
    payload: dict


class LarkCliFeishuClient:
    def __init__(self, cli_executable: str | None = None) -> None:
        self._cli_executable = cli_executable

    def ensure_ready(self) -> None:
        diagnosis = self.doctor()
        if not diagnosis.installed:
            raise LarkCliNotInstalledError(
                "lark-cli is not installed. Install it first, then configure and log in.",
                status="not_installed",
            )
        if not diagnosis.ready:
            raise LarkCliAuthError(
                diagnosis.hint or "lark-cli is not configured or authenticated.",
                status=diagnosis.status,
                hint=diagnosis.hint,
                recommended_command=diagnosis.recommended_command,
            )

    def doctor(self) -> LarkCliDoctorResult:
        executable = self._cli_executable or shutil.which("lark-cli")
        if executable is None:
            return LarkCliDoctorResult(
                installed=False,
                executable=None,
                ready=False,
                status="not_installed",
                hint="Install lark-cli first, then configure and log in.",
                recommended_command=None,
            )

        self._cli_executable = executable
        result = self._invoke_json(["auth", "status", "--json"], cwd=None)
        if result.returncode == 0 and result.payload.get("ok", True):
            return LarkCliDoctorResult(
                installed=True,
                executable=executable,
                ready=True,
                status="ready",
                hint=None,
                recommended_command=None,
            )

        error = result.payload.get("error", {})
        hint = error.get("hint") or error.get("message") or "lark-cli command failed."
        return LarkCliDoctorResult(
            installed=True,
            executable=executable,
            ready=False,
            status=self._status_from_error(error),
            hint=hint,
            recommended_command=self._recommended_command(error, hint),
        )

    def preferred_access_strategy(self) -> str:
        return "bot_first"

    def user_fallback_scopes(self) -> list[str]:
        return list(USER_FALLBACK_SCOPES)

    def find_child_folder(self, parent_token: str, name: str) -> str | None:
        payload = self._run_drive_json(
            [
                "drive",
                "files",
                "list",
                "--json",
                "--page-all",
                "--folder-token",
                parent_token,
            ],
            cwd=None,
        )
        files = self._unwrap_data(payload).get("files", [])
        matches = [
            item["token"]
            for item in files
            if item.get("type") == "folder" and item.get("name") == name
        ]
        if len(matches) > 1:
            raise RemoteFolderConflictError(
                f"Multiple remote folders named {name!r} exist under {parent_token}."
            )
        return matches[0] if matches else None

    def create_folder(self, parent_token: str, name: str) -> str:
        payload = self._run_drive_json(
            [
                "drive",
                "files",
                "create_folder",
                "--json",
                "--data",
                json.dumps({"folder_token": parent_token, "name": name}),
            ],
            cwd=None,
        )
        return self._unwrap_data(payload)["token"]

    def status(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> DriveDiffStatus:
        payload = self._run_drive_json(
            [
                "drive",
                "+status",
                "--json",
                "--local-dir",
                local_dir.relative_to(repo_root).as_posix(),
                "--folder-token",
                folder_token,
            ],
            cwd=repo_root,
        )
        data = self._unwrap_data(payload)
        return DriveDiffStatus(
            local_only=sorted(item["rel_path"] for item in data.get("new_local", [])),
            modified=sorted(item["rel_path"] for item in data.get("modified", [])),
            unchanged=sorted(item["rel_path"] for item in data.get("unchanged", [])),
            remote_only=sorted(item["rel_path"] for item in data.get("new_remote", [])),
        )

    def push(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> dict:
        payload = self._run_drive_json(
            [
                "drive",
                "+push",
                "--json",
                "--local-dir",
                local_dir.relative_to(repo_root).as_posix(),
                "--folder-token",
                folder_token,
                "--if-exists",
                "overwrite",
            ],
            cwd=repo_root,
        )
        return self._unwrap_data(payload)

    def pull(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> dict:
        payload = self._run_drive_json(
            [
                "drive",
                "+pull",
                "--json",
                "--local-dir",
                local_dir.relative_to(repo_root).as_posix(),
                "--folder-token",
                folder_token,
                "--if-exists",
                "overwrite",
            ],
            cwd=repo_root,
        )
        return self._unwrap_data(payload)

    def _run_json(self, args: list[str], cwd: Path | None) -> dict:
        result = self._invoke_json(args, cwd)
        if result.returncode != 0:
            payload = result.payload
            error = payload.get("error", {})
            hint = error.get("hint")
            message = error.get("message") or "lark-cli command failed."
            raise LarkCliError(
                hint or message,
                status=error.get("subtype") or error.get("type") or "command_error",
                hint=hint,
                recommended_command=error.get("recommended_command"),
            )
        return result.payload

    def _run_drive_json(self, args: list[str], cwd: Path | None) -> dict:
        result = self._invoke_drive_json(args, cwd)
        if result.returncode != 0:
            payload = result.payload
            error = payload.get("error", {})
            hint = error.get("hint")
            message = error.get("message") or "lark-cli command failed."
            raise LarkCliError(
                hint or message,
                status=error.get("subtype") or error.get("type") or "command_error",
                hint=hint,
                recommended_command=error.get("recommended_command"),
            )
        return result.payload

    def _unwrap_data(self, payload: dict) -> dict:
        if "data" in payload and isinstance(payload["data"], dict):
            return payload["data"]
        return payload

    def _resolve_cli_executable(self) -> str:
        if self._cli_executable is None:
            self._cli_executable = shutil.which("lark-cli")
        if self._cli_executable is None:
            raise LarkCliNotInstalledError(
                "lark-cli is not installed. Install it first, then configure and log in."
            )
        return self._cli_executable

    def _decode_output(self, output: bytes | str | None) -> str:
        if output is None:
            return ""
        if isinstance(output, str):
            return output
        return output.decode("utf-8", errors="replace")

    def _invoke_json(self, args: list[str], cwd: Path | None) -> _JsonCommandResult:
        try:
            completed = subprocess.run(
                [self._resolve_cli_executable(), *args],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LarkCliNotInstalledError("lark-cli is not installed.") from exc

        stdout = self._decode_output(completed.stdout).strip()
        stderr = self._decode_output(completed.stderr).strip()
        output = "\n".join(part for part in [stdout, stderr] if part)
        payload: dict = {}
        if output:
            parsed = self._extract_last_json_document(output)
            if parsed is not None:
                payload = parsed
            else:
                payload = {"error": {"message": output}}
        return _JsonCommandResult(returncode=completed.returncode, payload=payload)

    def _invoke_drive_json(self, args: list[str], cwd: Path | None) -> _JsonCommandResult:
        bot_result = self._invoke_json([*args, "--as", "bot"], cwd)
        if bot_result.returncode == 0:
            return bot_result

        bot_error = bot_result.payload.get("error", {})
        if not self._is_bot_resource_permission_error(bot_error):
            return bot_result

        auth_status = self._run_json(["auth", "status", "--json"], cwd=None)
        user_identity = (auth_status.get("identities") or {}).get("user") or {}
        if user_identity.get("available") and user_identity.get("status") == "ready":
            missing_scopes = self._missing_user_fallback_scopes(auth_status)
            if missing_scopes:
                return self._build_user_fallback_missing_scope_result(
                    missing_scopes,
                    returncode=1,
                )
            user_result = self._invoke_json([*args, "--as", "user"], cwd)
            if user_result.returncode == 0:
                return user_result

            user_error = user_result.payload.get("error", {})
            if self._is_user_missing_scope_error(user_error):
                returned_missing_scopes = user_error.get("missing_scopes") or []
                missing_scopes = self._ordered_unique_scopes(
                    [*self._missing_user_fallback_scopes(auth_status), *returned_missing_scopes]
                )
                return self._build_user_fallback_missing_scope_result(
                    missing_scopes,
                    returncode=user_result.returncode,
                )
            return user_result

        return _JsonCommandResult(
            returncode=bot_result.returncode,
            payload={
                "error": {
                    "type": "authorization",
                    "subtype": "user_identity_missing",
                    "message": bot_error.get("message") or "bot lacks permission for the requested resource",
                    "hint": (
                        "This folder is not accessible to the current bot identity. "
                        "Preferred path: keep bot-first and grant the bot access to the target folder. "
                        "Fallback path: authorize user identity once with the full required scopes and try again."
                    ),
                    "recommended_command": self._user_fallback_login_command(USER_FALLBACK_SCOPES),
                }
            },
        )

    def _status_from_error(self, error: dict) -> str:
        error_type = error.get("type")
        error_subtype = error.get("subtype")
        if error_type == "config" and error_subtype == "not_configured":
            return "not_configured"
        if error_type == "auth":
            return "not_authenticated"
        return "command_error"

    def _recommended_command(self, error: dict, hint: str) -> str | None:
        command = self._extract_backtick_command(hint)
        if command:
            return command
        error_type = error.get("type")
        error_subtype = error.get("subtype")
        if error_type == "config" and error_subtype == "not_configured":
            return "lark-cli config init --new"
        return None

    def _extract_backtick_command(self, text: str) -> str | None:
        match = re.search(r"`([^`]+)`", text)
        if match:
            return match.group(1).strip()
        return None

    def _extract_last_json_document(self, text: str) -> dict | None:
        decoder = json.JSONDecoder()
        docs: list[dict] = []
        index = 0
        while index < len(text):
            match = re.search(r"[{\[]", text[index:])
            if not match:
                break
            start = index + match.start()
            try:
                value, offset = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                index = start + 1
                continue
            if isinstance(value, dict):
                docs.append(value)
            index = start + offset
        return docs[-1] if docs else None

    def _is_bot_resource_permission_error(self, error: dict) -> bool:
        return (
            error.get("type") == "authorization"
            and error.get("subtype") == "permission_denied"
            and error.get("identity") == "bot"
        )

    def _is_user_missing_scope_error(self, error: dict) -> bool:
        return (
            error.get("type") == "authorization"
            and error.get("subtype") == "missing_scope"
            and error.get("identity") == "user"
        )

    def _missing_user_fallback_scopes(self, auth_status: dict) -> list[str]:
        user_identity = (auth_status.get("identities") or {}).get("user") or {}
        granted_scopes = {
            value.strip()
            for value in str(user_identity.get("scope", "")).split()
            if value.strip()
        }
        return [scope for scope in USER_FALLBACK_SCOPES if scope not in granted_scopes]

    def _user_fallback_login_command(self, scopes: tuple[str, ...] | list[str]) -> str:
        scope_string = " ".join(scopes)
        return f'lark-cli auth login --scope "{scope_string}" --no-wait --json'

    def _build_user_fallback_missing_scope_result(
        self,
        missing_scopes: list[str],
        *,
        returncode: int,
    ) -> _JsonCommandResult:
        scope_list = self._ordered_unique_scopes(missing_scopes)
        recommended_scopes = self._recommended_user_fallback_scopes(scope_list)
        return _JsonCommandResult(
            returncode=returncode,
            payload={
                "error": {
                    "type": "authorization",
                    "subtype": "missing_scope",
                    "identity": "user",
                    "message": "user authorization does not yet cover the full fallback scope set",
                    "hint": (
                        "Bot-first remains the preferred path. "
                        "If you need user-fallback, authorize the full one-time fallback scope set in a single login."
                    ),
                    "missing_scopes": scope_list,
                    "recommended_command": self._user_fallback_login_command(recommended_scopes),
                }
            },
        )

    def _ordered_unique_scopes(self, scopes: list[str]) -> list[str]:
        requested = [scope for scope in scopes if scope]
        requested_set = set(requested)
        ordered = [scope for scope in USER_FALLBACK_SCOPES if scope in requested_set]
        extras = [scope for scope in requested if scope not in USER_FALLBACK_SCOPES]
        return ordered + list(dict.fromkeys(extras))

    def _recommended_user_fallback_scopes(self, missing_scopes: list[str]) -> list[str]:
        return self._ordered_unique_scopes([*USER_FALLBACK_SCOPES, *missing_scopes])
