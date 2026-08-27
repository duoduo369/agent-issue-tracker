from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import CanonicalFile, ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar


@dataclass(frozen=True)
class PullPreview:
    feature_name: str
    resolved_repo_name: str
    remote_root_folder_token: str
    remote_repo_folder_token: str
    remote_feature_folder_token: str
    canonical_files: list[str]
    will_create: list[str]
    will_overwrite: list[str]
    unchanged: list[str]
    local_only_canonical: list[str]
    remote_extra_files: list[str]
    local_extra_files: list[str]
    confirmation_required: bool


@dataclass(frozen=True)
class PullExecutionResult:
    preview: PullPreview
    pull_result: dict


class PullConfirmationRequired(RuntimeError):
    def __init__(self, preview: PullPreview) -> None:
        super().__init__("Pull requires explicit confirmation.")
        self.preview = preview


class PullService:
    def __init__(self, *, layout_provider: ScratchLayoutProvider, feishu_client: object) -> None:
        self.layout_provider = layout_provider
        self.feishu_client = feishu_client

    def preview_pull(
        self,
        *,
        repo_root: Path,
        cwd: Path,
        feature_name: str | None,
        resolved_config: ResolvedConfig,
    ) -> PullPreview:
        feature = self.layout_provider.resolve_feature_name(
            repo_root=repo_root,
            cwd=cwd,
            explicit_feature=feature_name,
        )
        feature_dir = self.layout_provider.feature_dir(repo_root, feature)
        local_canonical_files = self.layout_provider.collect_canonical_files(feature_dir)
        local_extra_files = self.layout_provider.collect_local_extra_files(feature_dir)
        (
            resolved_repo_name,
            remote_root_token,
            remote_repo_folder_token,
            remote_feature_folder_token,
        ) = self._resolve_remote_feature(
            repo_root=repo_root,
            feature_name=feature,
            feature_dir=feature_dir,
            resolved_config=resolved_config,
        )

        with self._canonical_staging_dir(repo_root, local_canonical_files) as staging_dir:
            status_result = self.feishu_client.status(
                repo_root=repo_root,
                local_dir=staging_dir,
                folder_token=remote_feature_folder_token,
            )

        will_create = sorted(
            path
            for path in status_result.new_remote
            if self.layout_provider.is_canonical_rel_path(path)
        )
        remote_extra_files = sorted(
            path
            for path in status_result.new_remote
            if not self.layout_provider.is_canonical_rel_path(path)
        )
        canonical_files = sorted(
            {
                *(item.rel_path for item in local_canonical_files),
                *status_result.new_local,
                *status_result.modified,
                *status_result.unchanged,
                *will_create,
            }
        )
        confirmation_required = bool(
            status_result.modified
            or status_result.new_local
            or remote_extra_files
            or local_extra_files
        )
        return PullPreview(
            feature_name=feature,
            resolved_repo_name=resolved_repo_name,
            remote_root_folder_token=remote_root_token,
            remote_repo_folder_token=remote_repo_folder_token,
            remote_feature_folder_token=remote_feature_folder_token,
            canonical_files=canonical_files,
            will_create=will_create,
            will_overwrite=status_result.modified,
            unchanged=status_result.unchanged,
            local_only_canonical=status_result.new_local,
            remote_extra_files=remote_extra_files,
            local_extra_files=local_extra_files,
            confirmation_required=confirmation_required,
        )

    def execute_pull(
        self,
        *,
        repo_root: Path,
        cwd: Path,
        feature_name: str | None,
        resolved_config: ResolvedConfig,
        confirm: bool,
    ) -> PullExecutionResult:
        preview = self.preview_pull(
            repo_root=repo_root,
            cwd=cwd,
            feature_name=feature_name,
            resolved_config=resolved_config,
        )
        if not confirm:
            raise PullConfirmationRequired(preview)

        self.feishu_client.ensure_ready()
        feature_dir = self.layout_provider.feature_dir(repo_root, preview.feature_name)
        feature_dir.mkdir(parents=True, exist_ok=True)

        with _EmptyStagingDir(repo_root) as staging_dir:
            pull_result = self.feishu_client.pull(
                repo_root=repo_root,
                local_dir=staging_dir,
                folder_token=preview.remote_feature_folder_token,
            )
            for rel_path in preview.local_only_canonical:
                destination = self.layout_provider.restore_destination(feature_dir, rel_path)
                if destination.exists():
                    destination.unlink()
            for item in self.layout_provider.collect_canonical_files(staging_dir):
                destination = self.layout_provider.restore_destination(
                    feature_dir,
                    item.rel_path,
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.absolute_path, destination)

        FeatureSidecar(
            feature_name=preview.feature_name,
            resolved_repo_name=preview.resolved_repo_name,
            remote_root_folder_token=preview.remote_root_folder_token,
            remote_repo_folder_token=preview.remote_repo_folder_token,
            remote_feature_folder_token=preview.remote_feature_folder_token,
        ).save(feature_dir / self.layout_provider.sidecar_name)

        return PullExecutionResult(preview=preview, pull_result=pull_result)

    def _resolve_remote_feature(
        self,
        *,
        repo_root: Path,
        feature_name: str,
        feature_dir: Path,
        resolved_config: ResolvedConfig,
    ) -> tuple[str, str, str, str]:
        sidecar = FeatureSidecar.load(feature_dir / self.layout_provider.sidecar_name)
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
            remote_repo_folder_token = self.feishu_client.find_child_folder(
                remote_root_token,
                resolved_repo_name,
            )
        if remote_repo_folder_token is None:
            raise ValueError(
                f"Remote repo folder {resolved_repo_name!r} was not found under {remote_root_token}."
            )

        if remote_feature_folder_token is None:
            remote_feature_folder_token = self.feishu_client.find_child_folder(
                remote_repo_folder_token,
                feature_name,
            )
        if remote_feature_folder_token is None:
            raise ValueError(
                f"Remote feature folder {feature_name!r} was not found under repo {resolved_repo_name!r}."
            )

        return (
            resolved_repo_name,
            remote_root_token,
            remote_repo_folder_token,
            remote_feature_folder_token,
        )

    def _canonical_staging_dir(
        self,
        repo_root: Path,
        canonical_files: list[CanonicalFile],
    ) -> "_CanonicalStagingDir":
        return _CanonicalStagingDir(repo_root, canonical_files)


class _CanonicalStagingDir:
    def __init__(self, repo_root: Path, canonical_files: list[CanonicalFile]) -> None:
        self.repo_root = repo_root
        self.canonical_files = canonical_files
        self.path: Path | None = None

    def __enter__(self) -> Path:
        staging_root = Path(
            tempfile.mkdtemp(prefix=".feishu-sync-staging-", dir=self.repo_root)
        )
        for item in self.canonical_files:
            destination = staging_root / item.rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.absolute_path, destination)
        self.path = staging_root
        return staging_root

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path)


class _EmptyStagingDir:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix=".feishu-sync-staging-", dir=self.repo_root))
        return self.path

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self.path and self.path.exists():
            shutil.rmtree(self.path)
