from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.backend import PersistenceBackend
from feishu_issue_tracker.config import ResolvedConfig, resolve_target_repo_name
from feishu_issue_tracker.layout import CanonicalFile, ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar, load_backend_sidecar


@dataclass(frozen=True)
class BackendFeatureBinding:
    backend_name: str
    feature_name: str
    resolved_repo_name: str
    tracker_root_locator: str
    tracker_repo_locator: str | None
    tracker_feature_locator: str | None


def resolve_push_binding(
    *,
    repo_root: Path,
    feature_name: str,
    feature_dir: Path,
    resolved_config: ResolvedConfig,
    layout_provider: ScratchLayoutProvider,
    backend: PersistenceBackend,
) -> BackendFeatureBinding:
    sidecar = _load_matching_sidecar(
        feature_dir=feature_dir,
        backend_name=backend.backend_name,
        expected_feature_name=feature_name,
    )
    root_locator = (
        sidecar.root_locator
        if sidecar
        else backend.root_locator_from_config(resolved_config=resolved_config)
    )
    resolved_repo_name = (
        sidecar.resolved_repo_name
        if sidecar
        else resolve_target_repo_name(repo_root=repo_root, resolved_config=resolved_config)
    )
    repo_locator = sidecar.repo_locator if sidecar else None
    feature_locator = sidecar.feature_locator if sidecar else None

    if repo_locator is None:
        repo_locator = backend.find_remote_repo(
            root_locator=root_locator,
            repo_name=resolved_repo_name,
        )
    if feature_locator is None and repo_locator is not None:
        feature_locator = backend.find_remote_feature(
            repo_locator=repo_locator,
            feature_name=feature_name,
        )

    return BackendFeatureBinding(
        backend_name=backend.backend_name,
        feature_name=feature_name,
        resolved_repo_name=resolved_repo_name,
        tracker_root_locator=root_locator,
        tracker_repo_locator=repo_locator,
        tracker_feature_locator=feature_locator,
    )


def resolve_pull_binding(
    *,
    repo_root: Path,
    feature_name: str,
    feature_dir: Path,
    resolved_config: ResolvedConfig,
    layout_provider: ScratchLayoutProvider,
    backend: PersistenceBackend,
) -> BackendFeatureBinding:
    binding = resolve_push_binding(
        repo_root=repo_root,
        feature_name=feature_name,
        feature_dir=feature_dir,
        resolved_config=resolved_config,
        layout_provider=layout_provider,
        backend=backend,
    )

    if binding.tracker_repo_locator is None:
        raise ValueError(
            f"Tracker workspace repo {binding.resolved_repo_name!r} was not found under "
            f"{binding.tracker_root_locator} for backend {binding.backend_name!r}."
        )
    if binding.tracker_feature_locator is None:
        raise ValueError(
            f"Tracker workspace feature {feature_name!r} was not found under repo "
            f"{binding.resolved_repo_name!r} for backend {binding.backend_name!r}."
        )
    return binding


@contextmanager
def canonical_staging_dir(
    repo_root: Path,
    canonical_files: list[CanonicalFile],
) -> Iterator[Path]:
    staging_root = Path(tempfile.mkdtemp(prefix=".issue-tracker-staging-", dir=repo_root))
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
    staging_root = Path(tempfile.mkdtemp(prefix=".issue-tracker-staging-", dir=repo_root))
    try:
        yield staging_root
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def _load_matching_sidecar(
    *,
    feature_dir: Path,
    backend_name: str,
    expected_feature_name: str,
) -> FeatureSidecar | None:
    sidecar = load_backend_sidecar(feature_dir, backend_name)
    if sidecar is None or sidecar.feature_name != expected_feature_name:
        return None
    return sidecar
