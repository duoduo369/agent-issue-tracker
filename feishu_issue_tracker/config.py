from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

REQUIRED_CONFIG_KEYS = ["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"]
OPTIONAL_CONFIG_KEYS = ["FEISHU_ISSUE_TRACKER_REPO_NAME"]
ALL_CONFIG_KEYS = REQUIRED_CONFIG_KEYS + OPTIONAL_CONFIG_KEYS


@dataclass(frozen=True)
class ResolvedConfig:
    values: dict[str, str]
    sources: dict[str, str]
    missing_keys: list[str]
    user_config_path: Path


class UserConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            key: str(value)
            for key, value in data.items()
            if key in ALL_CONFIG_KEYS and isinstance(value, str) and value.strip()
        }

    def save(self, values: dict[str, str]) -> None:
        existing_values = self.load()
        filtered_values = {
            key: value
            for key, value in values.items()
            if key in ALL_CONFIG_KEYS and value.strip()
        }
        merged_values = {**existing_values, **filtered_values}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(merged_values, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def default_user_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "feishu-issue-tracker" / "config.json"
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "feishu-issue-tracker" / "config.json"
    return Path.home() / ".config" / "feishu-issue-tracker" / "config.json"


def resolve_config(
    *,
    repo_root: Path,
    env: dict[str, str] | None = None,
    user_config_store: UserConfigStore | None = None,
) -> ResolvedConfig:
    env_values = env if env is not None else dict(os.environ)
    user_store = user_config_store or UserConfigStore(default_user_config_path())
    repo_env_values = parse_dotenv(repo_root / ".env")
    user_values = user_store.load()

    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in ALL_CONFIG_KEYS:
        env_value = env_values.get(key, "").strip()
        repo_env_value = repo_env_values.get(key, "").strip()
        user_value = user_values.get(key, "").strip()
        if env_value:
            values[key] = env_value
            sources[key] = "env"
        elif repo_env_value:
            values[key] = repo_env_value
            sources[key] = "repo_env"
        elif user_value:
            values[key] = user_value
            sources[key] = "user"

    missing_keys = [key for key in REQUIRED_CONFIG_KEYS if key not in values]
    return ResolvedConfig(
        values=values,
        sources=sources,
        missing_keys=missing_keys,
        user_config_path=user_store.path,
    )


def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key not in ALL_CONFIG_KEYS:
            continue
        value = raw_value.strip().strip("'").strip('"')
        if value:
            values[key] = value
    return values
