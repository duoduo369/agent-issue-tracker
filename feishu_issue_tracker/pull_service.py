from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar
from feishu_issue_tracker.sync_common import (
    canonical_staging_dir,
    empty_staging_dir,
    resolve_pull_binding,
)


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

        binding = resolve_pull_binding(
            repo_root=repo_root,
            feature_name=feature,
            feature_dir=feature_dir,
            resolved_config=resolved_config,
            layout_provider=self.layout_provider,
            feishu_client=self.feishu_client,
        )

        with canonical_staging_dir(repo_root, local_canonical_files) as staging_dir:
            status_result = self.feishu_client.status(
                repo_root=repo_root,
                local_dir=staging_dir,
                folder_token=binding.remote_feature_folder_token,
            )

        will_create = sorted(
            path
            for path in status_result.remote_only
            if self.layout_provider.is_canonical_rel_path(path)
        )
        remote_extra_files = sorted(
            path
            for path in status_result.remote_only
            if not self.layout_provider.is_canonical_rel_path(path)
        )
        canonical_files = sorted(
            {
                *(item.rel_path for item in local_canonical_files),
                *status_result.local_only,
                *status_result.modified,
                *status_result.unchanged,
                *will_create,
            }
        )
        confirmation_required = bool(
            status_result.modified
            or status_result.local_only
            or remote_extra_files
            or local_extra_files
        )
        return PullPreview(
            feature_name=feature,
            resolved_repo_name=binding.resolved_repo_name,
            remote_root_folder_token=binding.remote_root_folder_token,
            remote_repo_folder_token=binding.remote_repo_folder_token,
            remote_feature_folder_token=binding.remote_feature_folder_token,
            canonical_files=canonical_files,
            will_create=will_create,
            will_overwrite=status_result.modified,
            unchanged=status_result.unchanged,
            local_only_canonical=status_result.local_only,
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
        if confirm:
            self.feishu_client.ensure_ready()
        preview = self.preview_pull(
            repo_root=repo_root,
            cwd=cwd,
            feature_name=feature_name,
            resolved_config=resolved_config,
        )
        if not confirm:
            raise PullConfirmationRequired(preview)

        feature_dir = self.layout_provider.feature_dir(repo_root, preview.feature_name)
        feature_dir.mkdir(parents=True, exist_ok=True)

        with empty_staging_dir(repo_root) as staging_dir:
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
