from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FeatureSidecar:
    backend_name: str
    feature_name: str
    resolved_repo_name: str
    root_locator: str
    repo_locator: str
    feature_locator: str

    @classmethod
    def load(cls, path: Path) -> FeatureSidecar | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            backend_name=data.get("backend_name") or _infer_backend_name(path),
            feature_name=data["feature_name"],
            resolved_repo_name=data["resolved_repo_name"],
            root_locator=data.get("root_locator") or data["remote_root_folder_token"],
            repo_locator=data.get("repo_locator") or data["remote_repo_folder_token"],
            feature_locator=data.get("feature_locator") or data["remote_feature_folder_token"],
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def sidecar_filename(backend_name: str) -> str:
    return f".issue-tracker.{backend_name}.json"


def sidecar_path(feature_dir: Path, backend_name: str) -> Path:
    return feature_dir / sidecar_filename(backend_name)


def load_backend_sidecar(feature_dir: Path, backend_name: str) -> FeatureSidecar | None:
    candidates = [sidecar_path(feature_dir, backend_name), *_legacy_sidecar_paths(feature_dir, backend_name)]
    for candidate in candidates:
        sidecar = FeatureSidecar.load(candidate)
        if sidecar is not None and sidecar.backend_name == backend_name:
            return sidecar
    return None


def _legacy_sidecar_paths(feature_dir: Path, backend_name: str) -> list[Path]:
    if backend_name == "feishu":
        return [feature_dir / ".feishu-sync.json"]
    return []


def _infer_backend_name(path: Path) -> str:
    name = path.name
    prefix = ".issue-tracker."
    suffix = ".json"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)]
    if name == ".feishu-sync.json":
        return "feishu"
    raise ValueError(f"Could not infer backend name from sidecar path {path}.")
