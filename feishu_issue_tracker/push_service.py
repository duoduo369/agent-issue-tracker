from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.sidecar import FeatureSidecar
from feishu_issue_tracker.sync_common import canonical_staging_dir, resolve_push_binding


@dataclass(frozen=True)
class PushPreview:
    feature_name: str
    resolved_repo_name: str
    remote_root_folder_token: str
    remote_repo_folder_token: str | None
    remote_feature_folder_token: str | None
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
    def __init__(self, *, layout_provider: ScratchLayoutProvider, feishu_client: object) -> None:
        self.layout_provider = layout_provider
        self.feishu_client = feishu_client

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
            feishu_client=self.feishu_client,
        )

        canonical_rel_paths = [item.rel_path for item in canonical_files]
        local_extra_files = self.layout_provider.collect_local_extra_files(feature_dir)

        if binding.remote_feature_folder_token is None:
            return PushPreview(
                feature_name=feature,
                resolved_repo_name=binding.resolved_repo_name,
                remote_root_folder_token=binding.remote_root_folder_token,
                remote_repo_folder_token=binding.remote_repo_folder_token,
                remote_feature_folder_token=None,
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
            status_result = self.feishu_client.status(
                repo_root=repo_root,
                local_dir=staging_dir,
                folder_token=binding.remote_feature_folder_token,
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
            feature_name=feature,
            resolved_repo_name=binding.resolved_repo_name,
            remote_root_folder_token=binding.remote_root_folder_token,
            remote_repo_folder_token=binding.remote_repo_folder_token,
            remote_feature_folder_token=binding.remote_feature_folder_token,
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
            self.feishu_client.ensure_ready()
        preview = self.preview_push(
            repo_root=repo_root,
            cwd=cwd,
            feature_name=feature_name,
            resolved_config=resolved_config,
        )
        if not confirm:
            raise PushConfirmationRequired(preview)

        remote_repo_folder_token = preview.remote_repo_folder_token
        if remote_repo_folder_token is None:
            remote_repo_folder_token = self.feishu_client.create_folder(
                preview.remote_root_folder_token,
                preview.resolved_repo_name,
            )
        remote_feature_folder_token = preview.remote_feature_folder_token
        if remote_feature_folder_token is None:
            remote_feature_folder_token = self.feishu_client.create_folder(
                remote_repo_folder_token,
                preview.feature_name,
            )

        feature_dir = self.layout_provider.feature_dir(repo_root, preview.feature_name)
        canonical_files = self.layout_provider.collect_canonical_files(feature_dir)
        with canonical_staging_dir(repo_root, canonical_files) as staging_dir:
            push_result = self.feishu_client.push(
                repo_root=repo_root,
                local_dir=staging_dir,
                folder_token=remote_feature_folder_token,
            )

        FeatureSidecar(
            feature_name=preview.feature_name,
            resolved_repo_name=preview.resolved_repo_name,
            remote_root_folder_token=preview.remote_root_folder_token,
            remote_repo_folder_token=remote_repo_folder_token,
            remote_feature_folder_token=remote_feature_folder_token,
        ).save(feature_dir / self.layout_provider.sidecar_name)

        final_preview = PushPreview(
            feature_name=preview.feature_name,
            resolved_repo_name=preview.resolved_repo_name,
            remote_root_folder_token=preview.remote_root_folder_token,
            remote_repo_folder_token=remote_repo_folder_token,
            remote_feature_folder_token=remote_feature_folder_token,
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
