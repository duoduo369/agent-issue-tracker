from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class LarkCliError(RuntimeError):
    pass


class LarkCliNotInstalledError(LarkCliError):
    pass


class LarkCliAuthError(LarkCliError):
    pass


class RemoteFolderConflictError(LarkCliError):
    pass


@dataclass(frozen=True)
class StatusResult:
    new_local: list[str]
    modified: list[str]
    unchanged: list[str]
    new_remote: list[str]


class LarkCliFeishuClient:
    def ensure_ready(self) -> None:
        if shutil.which("lark-cli") is None:
            raise LarkCliNotInstalledError(
                "lark-cli is not installed. Install it first, then configure and log in."
            )
        try:
            payload = self._run_json(["lark-cli", "auth", "status", "--json"], cwd=None)
        except LarkCliError as exc:
            raise LarkCliAuthError(str(exc)) from exc
        if not payload.get("ok", True):
            error = payload.get("error", {})
            raise LarkCliAuthError(
                error.get("hint")
                or error.get("message")
                or "lark-cli is not configured or authenticated."
            )

    def find_child_folder(self, parent_token: str, name: str) -> str | None:
        payload = self._run_json(
            [
                "lark-cli",
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
        payload = self._run_json(
            [
                "lark-cli",
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

    def status(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> StatusResult:
        payload = self._run_json(
            [
                "lark-cli",
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
        return StatusResult(
            new_local=sorted(item["rel_path"] for item in data.get("new_local", [])),
            modified=sorted(item["rel_path"] for item in data.get("modified", [])),
            unchanged=sorted(item["rel_path"] for item in data.get("unchanged", [])),
            new_remote=sorted(item["rel_path"] for item in data.get("new_remote", [])),
        )

    def push(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> dict:
        payload = self._run_json(
            [
                "lark-cli",
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

    def _run_json(self, args: list[str], cwd: Path | None) -> dict:
        try:
            completed = subprocess.run(
                args,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LarkCliNotInstalledError("lark-cli is not installed.") from exc
        output = completed.stdout.strip() or completed.stderr.strip()
        payload = json.loads(output) if output else {}
        if completed.returncode != 0:
            error = payload.get("error", {})
            hint = error.get("hint")
            message = error.get("message") or "lark-cli command failed."
            raise LarkCliError(hint or message)
        return payload

    def _unwrap_data(self, payload: dict) -> dict:
        if "data" in payload and isinstance(payload["data"], dict):
            return payload["data"]
        return payload
