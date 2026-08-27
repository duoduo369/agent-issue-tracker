from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REQUIRED_CONFIG_KEYS = ["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"]
OPTIONAL_CONFIG_KEYS = ["FEISHU_ISSUE_TRACKER_REPO_NAME"]
ALL_CONFIG_KEYS = REQUIRED_CONFIG_KEYS + OPTIONAL_CONFIG_KEYS
USER_CONFIG_DIRNAME = "feishu-issue-tracker"
USER_CONFIG_FILENAME = "config.env"


@dataclass(frozen=True)
class ResolvedConfig:
    values: dict[str, str]
    sources: dict[str, str]
    missing_keys: list[str]
    user_config_path: Path | None = None


def resolve_config(
    *,
    repo_root: Path,
    env: dict[str, str] | None = None,
    user_config_path: Path | None = None,
) -> ResolvedConfig:
    env_values = env if env is not None else dict(os.environ)
    repo_env_values = parse_dotenv(repo_root / ".env")
    resolved_user_config_path = user_config_path or default_user_config_path(env_values)
    user_env_values = parse_dotenv(resolved_user_config_path)

    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in ALL_CONFIG_KEYS:
        env_value = env_values.get(key, "").strip()
        repo_env_value = repo_env_values.get(key, "").strip()
        user_env_value = user_env_values.get(key, "").strip()
        if env_value:
            values[key] = env_value
            sources[key] = "env"
        elif repo_env_value:
            values[key] = repo_env_value
            sources[key] = "repo_env"
        elif user_env_value:
            values[key] = user_env_value
            sources[key] = "user_env"

    missing_keys = [key for key in REQUIRED_CONFIG_KEYS if key not in values]
    return ResolvedConfig(
        values=values,
        sources=sources,
        missing_keys=missing_keys,
        user_config_path=resolved_user_config_path,
    )


def default_user_config_path(env: dict[str, str] | None = None) -> Path:
    env_values = env if env is not None else dict(os.environ)
    if os.name == "nt":
        appdata = env_values.get("APPDATA")
        base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg_config_home = env_values.get("XDG_CONFIG_HOME")
        base_dir = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base_dir / USER_CONFIG_DIRNAME / USER_CONFIG_FILENAME


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
