from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.backend import PersistenceBackend
from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar, sidecar_path
from feishu_issue_tracker.sync_common import canonical_staging_dir, resolve_push_binding


@dataclass(frozen=True)
class PushPreview:
    backend_name: str
    feature_name: str
    resolved_repo_name: str
    tracker_root_locator: str
    tracker_repo_locator: str | None
    tracker_feature_locator: str | None
    canonical_files: list[str]
    will_create: list[str]
    will_overwrite: list[str]
    unchanged: list[str]
    remote_only_canonical: list[str]
    remote_extra_files: list[str]
    local_extra_files: list[str]
    confirmation_required: bool


@dataclass(frozen=True)
class PushExecutionResult:
    preview: PushPreview
    push_result: dict


class PushConfirmationRequired(RuntimeError):
    def __init__(self, preview: PushPreview) -> None:
        super().__init__("Push requires explicit confirmation.")
        self.preview = preview


class PushService:
    def __init__(self, *, layout_provider: ScratchLayoutProvider, backend: PersistenceBackend) -> None:
        self.layout_provider = layout_provider
        self.backend = backend

    def preview_push(
        self,
        *,
        repo_root: Path,
        cwd: Path,
        feature_name: str | None,
        resolved_config: ResolvedConfig,
    ) -> PushPreview:
        feature = self.layout_provider.resolve_feature_name(
            repo_root=repo_root,
            cwd=cwd,
            explicit_feature=feature_name,
        )
        feature_dir = self.layout_provider.feature_dir(repo_root, feature)
        canonical_files = self.layout_provider.collect_canonical_files(feature_dir)
        if not canonical_files:
            raise ValueError(f"No canonical files found under {feature_dir}")

        binding = resolve_push_binding(
            repo_root=repo_root,
            feature_name=feature,
            feature_dir=feature_dir,
            resolved_config=resolved_config,
            layout_provider=self.layout_provider,
            backend=self.backend,
        )

        canonical_rel_paths = [item.rel_path for item in canonical_files]
        local_extra_files = self.layout_provider.collect_local_extra_files(feature_dir)

        if binding.tracker_feature_locator is None:
            return PushPreview(
                backend_name=binding.backend_name,
                feature_name=feature,
                resolved_repo_name=binding.resolved_repo_name,
                tracker_root_locator=binding.tracker_root_locator,
                tracker_repo_locator=binding.tracker_repo_locator,
                tracker_feature_locator=None,
                canonical_files=canonical_rel_paths,
                will_create=canonical_rel_paths,
                will_overwrite=[],
                unchanged=[],
                remote_only_canonical=[],
                remote_extra_files=[],
                local_extra_files=local_extra_files,
                confirmation_required=bool(local_extra_files),
            )

        with canonical_staging_dir(repo_root, canonical_files) as staging_dir:
            status_result = self.backend.status(
                repo_root=repo_root,
                local_dir=staging_dir,
                remote_locator=binding.tracker_feature_locator,
            )

        remote_only_canonical = [
            path for path in status_result.remote_only if self.layout_provider.is_canonical_rel_path(path)
        ]
        remote_extra_files = [
            path for path in status_result.remote_only if not self.layout_provider.is_canonical_rel_path(path)
        ]
        confirmation_required = bool(
            status_result.modified
            or remote_only_canonical
            or remote_extra_files
            or local_extra_files
        )
        return PushPreview(
            backend_name=binding.backend_name,
            feature_name=feature,
            resolved_repo_name=binding.resolved_repo_name,
            tracker_root_locator=binding.tracker_root_locator,
            tracker_repo_locator=binding.tracker_repo_locator,
            tracker_feature_locator=binding.tracker_feature_locator,
            canonical_files=canonical_rel_paths,
            will_create=status_result.local_only,
            will_overwrite=status_result.modified,
            unchanged=status_result.unchanged,
            remote_only_canonical=remote_only_canonical,
            remote_extra_files=remote_extra_files,
            local_extra_files=local_extra_files,
            confirmation_required=confirmation_required,
        )

    def execute_push(
        self,
        *,
        repo_root: Path,
        cwd: Path,
        feature_name: str | None,
        resolved_config: ResolvedConfig,
        confirm: bool,
    ) -> PushExecutionResult:
        if confirm:
            self.backend.ensure_ready()
        preview = self.preview_push(
            repo_root=repo_root,
            cwd=cwd,
            feature_name=feature_name,
            resolved_config=resolved_config,
        )
        if not confirm:
            raise PushConfirmationRequired(preview)

        tracker_repo_locator = preview.tracker_repo_locator
        if tracker_repo_locator is None:
            tracker_repo_locator = self.backend.create_remote_repo(
                root_locator=preview.tracker_root_locator,
                repo_name=preview.resolved_repo_name,
            )
        tracker_feature_locator = preview.tracker_feature_locator
        if tracker_feature_locator is None:
            tracker_feature_locator = self.backend.create_remote_feature(
                repo_locator=tracker_repo_locator,
                feature_name=preview.feature_name,
            )

        feature_dir = self.layout_provider.feature_dir(repo_root, preview.feature_name)
        canonical_files = self.layout_provider.collect_canonical_files(feature_dir)
        with canonical_staging_dir(repo_root, canonical_files) as staging_dir:
            push_result = self.backend.push(
                repo_root=repo_root,
                local_dir=staging_dir,
                remote_locator=tracker_feature_locator,
            )

        FeatureSidecar(
            backend_name=preview.backend_name,
            feature_name=preview.feature_name,
            resolved_repo_name=preview.resolved_repo_name,
            root_locator=preview.tracker_root_locator,
            repo_locator=tracker_repo_locator,
            feature_locator=tracker_feature_locator,
        ).save(sidecar_path(feature_dir, preview.backend_name))

        final_preview = PushPreview(
            backend_name=preview.backend_name,
            feature_name=preview.feature_name,
            resolved_repo_name=preview.resolved_repo_name,
            tracker_root_locator=preview.tracker_root_locator,
            tracker_repo_locator=tracker_repo_locator,
            tracker_feature_locator=tracker_feature_locator,
            canonical_files=preview.canonical_files,
            will_create=preview.will_create,
            will_overwrite=preview.will_overwrite,
            unchanged=preview.unchanged,
            remote_only_canonical=preview.remote_only_canonical,
            remote_extra_files=preview.remote_extra_files,
            local_extra_files=preview.local_extra_files,
            confirmation_required=preview.confirmation_required,
        )
        return PushExecutionResult(preview=final_preview, push_result=push_result)
