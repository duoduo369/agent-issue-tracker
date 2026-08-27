from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_KEY = "AGENT_ISSUE_TRACKER_BACKEND"
REPO_NAME_KEY = "AGENT_ISSUE_TRACKER_REPO_NAME"
FEISHU_ROOT_FOLDER_TOKEN_KEY = "AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN"
GIT_REPO_PATH_KEY = "AGENT_ISSUE_TRACKER_GIT_REPO_PATH"
GIT_BRANCH_KEY = "AGENT_ISSUE_TRACKER_GIT_BRANCH"
LEGACY_CONFIG_ALIASES = {
    BACKEND_KEY: ["ISSUE_TRACKER_BACKEND"],
    REPO_NAME_KEY: ["ISSUE_TRACKER_REPO_NAME", "FEISHU_ISSUE_TRACKER_REPO_NAME"],
    FEISHU_ROOT_FOLDER_TOKEN_KEY: ["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"],
    GIT_REPO_PATH_KEY: ["ISSUE_TRACKER_GIT_REPO_PATH"],
    GIT_BRANCH_KEY: ["ISSUE_TRACKER_GIT_BRANCH"],
}
CANONICAL_CONFIG_KEYS = [
    BACKEND_KEY,
    REPO_NAME_KEY,
    FEISHU_ROOT_FOLDER_TOKEN_KEY,
    GIT_REPO_PATH_KEY,
    GIT_BRANCH_KEY,
]
BACKEND_REQUIRED_CONFIG_KEYS = {
    "feishu": [FEISHU_ROOT_FOLDER_TOKEN_KEY],
    "git": [GIT_REPO_PATH_KEY],
}
REQUIRED_CONFIG_KEYS = [BACKEND_KEY]
OPTIONAL_CONFIG_KEYS = [REPO_NAME_KEY, GIT_BRANCH_KEY]
ALL_CONFIG_KEYS = [
    *CANONICAL_CONFIG_KEYS,
    *(alias for aliases in LEGACY_CONFIG_ALIASES.values() for alias in aliases),
]
USER_CONFIG_DIRNAME = "agent-issue-tracker"
USER_CONFIG_FILENAME = "config.env"
LEGACY_USER_CONFIG_DIRNAMES = ["feishu-issue-tracker"]


@dataclass(frozen=True)
class ResolvedConfig:
    backend: str
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
    legacy_user_env_values = _load_legacy_user_env_values(
        env_values=env_values,
        resolved_user_config_path=resolved_user_config_path,
    )

    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for key in CANONICAL_CONFIG_KEYS:
        aliases = [key, *LEGACY_CONFIG_ALIASES.get(key, [])]
        resolved = _resolve_config_value(
            aliases=aliases,
            env_values=env_values,
            repo_env_values=repo_env_values,
            user_env_values={**legacy_user_env_values, **user_env_values},
        )
        if resolved is None:
            continue
        value, source = resolved
        values[key] = value
        sources[key] = source

    backend = values.get(BACKEND_KEY, "").strip().lower()
    if not backend:
        return ResolvedConfig(
            backend="",
            values=values,
            sources=sources,
            missing_keys=[BACKEND_KEY],
            user_config_path=resolved_user_config_path,
        )
    if backend not in BACKEND_REQUIRED_CONFIG_KEYS:
        raise ValueError(
            f"Unsupported {BACKEND_KEY} {backend!r}; expected one of "
            f"{', '.join(sorted(BACKEND_REQUIRED_CONFIG_KEYS))}."
        )

    missing_keys = [key for key in BACKEND_REQUIRED_CONFIG_KEYS[backend] if key not in values]
    return ResolvedConfig(
        backend=backend,
        values=values,
        sources=sources,
        missing_keys=missing_keys,
        user_config_path=resolved_user_config_path,
    )


def default_user_config_path(env: dict[str, str] | None = None) -> Path:
    env_values = env if env is not None else dict(os.environ)
    return _config_base_dir(env_values) / USER_CONFIG_DIRNAME / USER_CONFIG_FILENAME


def default_legacy_user_config_paths(env: dict[str, str] | None = None) -> list[Path]:
    env_values = env if env is not None else dict(os.environ)
    base_dir = _config_base_dir(env_values)
    return [base_dir / dirname / USER_CONFIG_FILENAME for dirname in LEGACY_USER_CONFIG_DIRNAMES]


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


def resolve_target_repo_name(*, repo_root: Path, resolved_config: ResolvedConfig) -> str:
    return resolved_config.values.get(REPO_NAME_KEY) or repo_root.name


def _resolve_config_value(
    *,
    aliases: list[str],
    env_values: dict[str, str],
    repo_env_values: dict[str, str],
    user_env_values: dict[str, str],
) -> tuple[str, str] | None:
    for source_name, source_values in (
        ("env", env_values),
        ("repo_env", repo_env_values),
        ("user_env", user_env_values),
    ):
        for key in aliases:
            value = source_values.get(key, "").strip()
            if value:
                return value, source_name
    return None


def _load_legacy_user_env_values(
    *,
    env_values: dict[str, str],
    resolved_user_config_path: Path,
) -> dict[str, str]:
    if resolved_user_config_path != default_user_config_path(env_values):
        return {}

    legacy_values: dict[str, str] = {}
    for path in default_legacy_user_config_paths(env_values):
        for key, value in parse_dotenv(path).items():
            legacy_values.setdefault(key, value)
    return legacy_values


def _config_base_dir(env_values: dict[str, str]) -> Path:
    if os.name == "nt":
        appdata = env_values.get("APPDATA")
        return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"

    xdg_config_home = env_values.get("XDG_CONFIG_HOME")
    return Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
