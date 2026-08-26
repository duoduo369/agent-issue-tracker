from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FeatureSidecar:
    feature_name: str
    resolved_repo_name: str
    remote_root_folder_token: str
    remote_repo_folder_token: str
    remote_feature_folder_token: str

    @classmethod
    def load(cls, path: Path) -> FeatureSidecar | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            feature_name=data["feature_name"],
            resolved_repo_name=data["resolved_repo_name"],
            remote_root_folder_token=data["remote_root_folder_token"],
            remote_repo_folder_token=data["remote_repo_folder_token"],
            remote_feature_folder_token=data["remote_feature_folder_token"],
        )

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
