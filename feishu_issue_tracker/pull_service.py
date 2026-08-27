from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.backend import PersistenceBackend
from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar, sidecar_path
from feishu_issue_tracker.sync_common import (
    canonical_staging_dir,
    empty_staging_dir,
    resolve_pull_binding,
)


@dataclass(frozen=True)
class PullPreview:
    backend_name: str
    feature_name: str
    resolved_repo_name: str
    tracker_root_locator: str
    tracker_repo_locator: str
    tracker_feature_locator: str
    canonical_files: list[str]
    will_create: list[str]
    will_overwrite: list[str]
    unchanged: list[str]
    local_only_canonical: list[str]
    remote_extra_files: list[str]
    local_extra_files: list[str]
    overwrite_hint: str
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
    def __init__(self, *, layout_provider: ScratchLayoutProvider, backend: PersistenceBackend) -> None:
        self.layout_provider = layout_provider
        self.backend = backend

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
            backend=self.backend,
        )

        with canonical_staging_dir(repo_root, local_canonical_files) as staging_dir:
            status_result = self.backend.status(
                repo_root=repo_root,
                local_dir=staging_dir,
                remote_locator=binding.tracker_feature_locator,
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
            backend_name=binding.backend_name,
            feature_name=feature,
            resolved_repo_name=binding.resolved_repo_name,
            tracker_root_locator=binding.tracker_root_locator,
            tracker_repo_locator=binding.tracker_repo_locator,
            tracker_feature_locator=binding.tracker_feature_locator,
            canonical_files=canonical_files,
            will_create=will_create,
            will_overwrite=status_result.modified,
            unchanged=status_result.unchanged,
            local_only_canonical=status_result.local_only,
            remote_extra_files=remote_extra_files,
            local_extra_files=local_extra_files,
            overwrite_hint=(
                "Pull treats the tracker workspace copy as the source of truth and "
                "restores canonical files over the source repo."
            ),
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
            self.backend.ensure_ready()
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
            pull_result = self.backend.pull(
                repo_root=repo_root,
                local_dir=staging_dir,
                remote_locator=preview.tracker_feature_locator,
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
            backend_name=preview.backend_name,
            feature_name=preview.feature_name,
            resolved_repo_name=preview.resolved_repo_name,
            root_locator=preview.tracker_root_locator,
            repo_locator=preview.tracker_repo_locator,
            feature_locator=preview.tracker_feature_locator,
        ).save(sidecar_path(feature_dir, preview.backend_name))

        return PullExecutionResult(preview=preview, pull_result=pull_result)
