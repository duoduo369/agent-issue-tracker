from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import CanonicalFile, ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar


@dataclass(frozen=True)
class RemoteFeatureBinding:
    feature_name: str
    resolved_repo_name: str
    remote_root_folder_token: str
    remote_repo_folder_token: str | None
    remote_feature_folder_token: str | None


def resolve_push_binding(
    *,
    repo_root: Path,
    feature_name: str,
    feature_dir: Path,
    resolved_config: ResolvedConfig,
    layout_provider: ScratchLayoutProvider,
    feishu_client: object,
) -> RemoteFeatureBinding:
    sidecar = _load_matching_sidecar(
        feature_dir / layout_provider.sidecar_name,
        expected_feature_name=feature_name,
    )
    remote_root_token = (
        sidecar.remote_root_folder_token
        if sidecar
        else resolved_config.values["FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN"]
    )
    resolved_repo_name = (
        sidecar.resolved_repo_name
        if sidecar
        else resolved_config.values.get("FEISHU_ISSUE_TRACKER_REPO_NAME", repo_root.name)
    )
    remote_repo_folder_token = sidecar.remote_repo_folder_token if sidecar else None
    remote_feature_folder_token = sidecar.remote_feature_folder_token if sidecar else None

    if remote_repo_folder_token is None:
        remote_repo_folder_token = feishu_client.find_child_folder(
            remote_root_token,
            resolved_repo_name,
        )
    if remote_feature_folder_token is None and remote_repo_folder_token is not None:
        remote_feature_folder_token = feishu_client.find_child_folder(
            remote_repo_folder_token,
            feature_name,
        )

    return RemoteFeatureBinding(
        feature_name=feature_name,
        resolved_repo_name=resolved_repo_name,
        remote_root_folder_token=remote_root_token,
        remote_repo_folder_token=remote_repo_folder_token,
        remote_feature_folder_token=remote_feature_folder_token,
    )


def resolve_pull_binding(
    *,
    repo_root: Path,
    feature_name: str,
    feature_dir: Path,
    resolved_config: ResolvedConfig,
    layout_provider: ScratchLayoutProvider,
    feishu_client: object,
) -> RemoteFeatureBinding:
    binding = resolve_push_binding(
        repo_root=repo_root,
        feature_name=feature_name,
        feature_dir=feature_dir,
        resolved_config=resolved_config,
        layout_provider=layout_provider,
        feishu_client=feishu_client,
    )

    if binding.remote_repo_folder_token is None:
        raise ValueError(
            f"Remote repo folder {binding.resolved_repo_name!r} was not found under "
            f"{binding.remote_root_folder_token}."
        )
    if binding.remote_feature_folder_token is None:
        raise ValueError(
            f"Remote feature folder {feature_name!r} was not found under repo "
            f"{binding.resolved_repo_name!r}."
        )
    return binding


@contextmanager
def canonical_staging_dir(
    repo_root: Path,
    canonical_files: list[CanonicalFile],
) -> Iterator[Path]:
    staging_root = Path(tempfile.mkdtemp(prefix=".feishu-sync-staging-", dir=repo_root))
    try:
        for item in canonical_files:
            destination = staging_root / item.rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.absolute_path, destination)
        yield staging_root
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


@contextmanager
def empty_staging_dir(repo_root: Path) -> Iterator[Path]:
    staging_root = Path(tempfile.mkdtemp(prefix=".feishu-sync-staging-", dir=repo_root))
    try:
        yield staging_root
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def _load_matching_sidecar(
    path: Path,
    *,
    expected_feature_name: str,
) -> FeatureSidecar | None:
    sidecar = FeatureSidecar.load(path)
    if sidecar is None or sidecar.feature_name != expected_feature_name:
        return None
    return sidecar
