import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import (
    FEISHU_ROOT_FOLDER_TOKEN_KEY,
    REPO_NAME_KEY,
    ResolvedConfig,
)
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.push_service import PushConfirmationRequired, PushService
from feishu_issue_tracker.sidecar import FeatureSidecar, sidecar_path


@dataclass
class FakeStatusResult:
    local_only: list[str]
    modified: list[str]
    unchanged: list[str]
    remote_only: list[str]


class FakeBackend:
    backend_name = "feishu"

    def __init__(self) -> None:
        self.ready_checks = 0
        self.status_calls: list[tuple[str, str]] = []
        self.push_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, tuple[str, ...]]] = []
        self.created_folders: list[tuple[str, str]] = []
        self.child_folders: dict[tuple[str, str], str] = {}
        self.status_result = FakeStatusResult(
            local_only=["spec.md"],
            modified=["issues/01.md"],
            unchanged=["map.md"],
            remote_only=["issues/02.md", "notes.txt"],
        )
        self.push_result = {
            "summary": {
                "uploaded": 1,
                "skipped": 1,
                "failed": 0,
                "deleted_remote": 0,
                "aborted": False,
            },
            "items": [
                {"rel_path": "spec.md", "file_token": "file-spec", "action": "uploaded"},
            ],
        }

    def ensure_ready(self) -> None:
        self.ready_checks += 1

    def root_locator_from_config(self, *, resolved_config: ResolvedConfig) -> str:
        return resolved_config.values[FEISHU_ROOT_FOLDER_TOKEN_KEY]

    def find_remote_repo(self, *, root_locator: str, repo_name: str) -> str | None:
        return self.child_folders.get((root_locator, repo_name))

    def find_remote_feature(self, *, repo_locator: str, feature_name: str) -> str | None:
        return self.child_folders.get((repo_locator, feature_name))

    def create_remote_repo(self, *, root_locator: str, repo_name: str) -> str:
        token = f"{root_locator}/{repo_name}"
        self.created_folders.append((root_locator, repo_name))
        self.child_folders[(root_locator, repo_name)] = token
        return token

    def create_remote_feature(self, *, repo_locator: str, feature_name: str) -> str:
        token = f"{repo_locator}/{feature_name}"
        self.created_folders.append((repo_locator, feature_name))
        self.child_folders[(repo_locator, feature_name)] = token
        return token

    def status(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> FakeStatusResult:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.status_calls.append((rel_local_dir, remote_locator))
        return self.status_result

    def delete_remote_paths(self, *, remote_locator: str, rel_paths: list[str]) -> int:
        self.delete_calls.append((remote_locator, tuple(rel_paths)))
        return len(rel_paths)

    def push(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> dict:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.push_calls.append((rel_local_dir, remote_locator))
        return self.push_result


class PushServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        (self.repo_root / ".git").mkdir()
        feature_dir = self.repo_root / ".scratch" / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
        (feature_dir / "map.md").write_text("# map\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# issue 1\n", encoding="utf-8")
        (feature_dir / "draft.txt").write_text("scratch note\n", encoding="utf-8")
        self.feature_dir = feature_dir
        self.sidecar_path = sidecar_path(feature_dir, "feishu")
        self.backend = FakeBackend()
        self.backend.child_folders[("root-folder", "remote-repo")] = "root-folder/remote-repo"
        self.backend.child_folders[("root-folder/remote-repo", "feature-a")] = (
            "root-folder/remote-repo/feature-a"
        )
        self.service = PushService(
            layout_provider=ScratchLayoutProvider(),
            backend=self.backend,
        )
        self.config = ResolvedConfig(
            backend="feishu",
            values={
                FEISHU_ROOT_FOLDER_TOKEN_KEY: "root-folder",
                REPO_NAME_KEY: "remote-repo",
            },
            sources={
                FEISHU_ROOT_FOLDER_TOKEN_KEY: "env",
                REPO_NAME_KEY: "env",
            },
            missing_keys=[],
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_preview_classifies_canonical_and_extra_files(self) -> None:
        preview = self.service.preview_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.feature_name, "feature-a")
        self.assertEqual(preview.will_create, ["spec.md"])
        self.assertEqual(preview.will_overwrite, ["issues/01.md"])
        self.assertEqual(preview.remote_only_canonical, ["issues/02.md"])
        self.assertEqual(preview.remote_extra_files, ["notes.txt"])
        self.assertEqual(preview.local_extra_files, ["draft.txt"])
        self.assertTrue(preview.confirmation_required)
        self.assertEqual(preview.backend_name, "feishu")
        self.assertEqual(preview.tracker_feature_locator, "root-folder/remote-repo/feature-a")
        self.assertEqual(self.backend.status_calls[0][1], "root-folder/remote-repo/feature-a")

    def test_execute_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(PushConfirmationRequired):
            self.service.execute_push(
                repo_root=self.repo_root,
                cwd=self.feature_dir,
                feature_name=None,
                resolved_config=self.config,
                confirm=False,
            )

    def test_execute_pushes_canonical_files_and_updates_sidecar(self) -> None:
        result = self.service.execute_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
            confirm=True,
        )

        self.assertEqual(self.backend.ready_checks, 1)
        self.assertEqual(result.preview.resolved_repo_name, "remote-repo")
        self.assertEqual(
            self.backend.delete_calls,
            [("root-folder/remote-repo/feature-a", ("issues/02.md",))],
        )
        self.assertEqual(result.push_result["summary"]["deleted_remote"], 1)
        self.assertEqual(self.backend.push_calls[0][1], "root-folder/remote-repo/feature-a")
        sidecar = FeatureSidecar.load(self.sidecar_path)
        self.assertEqual(sidecar.backend_name, "feishu")
        self.assertEqual(sidecar.feature_locator, "root-folder/remote-repo/feature-a")
        self.assertEqual(sidecar.resolved_repo_name, "remote-repo")

    def test_reuses_existing_sidecar_mapping(self) -> None:
        FeatureSidecar(
            backend_name="feishu",
            feature_name="feature-a",
            resolved_repo_name="stable-repo",
            root_locator="stable-root",
            repo_locator="stable-root/stable-repo",
            feature_locator="stable-root/stable-repo/feature-a",
        ).save(self.sidecar_path)

        preview = self.service.preview_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "stable-repo")
        self.assertEqual(self.backend.status_calls[0][1], "stable-root/stable-repo/feature-a")

    def test_ignores_sidecar_mapping_when_feature_name_does_not_match(self) -> None:
        FeatureSidecar(
            backend_name="feishu",
            feature_name="feature-b",
            resolved_repo_name="stable-repo",
            root_locator="stable-root",
            repo_locator="stable-root/stable-repo",
            feature_locator="stable-root/stable-repo/feature-b",
        ).save(self.sidecar_path)

        preview = self.service.preview_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "remote-repo")
        self.assertEqual(self.backend.status_calls[0][1], "root-folder/remote-repo/feature-a")

    def test_ignores_other_backend_sidecar(self) -> None:
        FeatureSidecar(
            backend_name="git",
            feature_name="feature-a",
            resolved_repo_name="git-repo",
            root_locator="git-root",
            repo_locator="git-root/git-repo",
            feature_locator="git-root/git-repo/feature-a",
        ).save(sidecar_path(self.feature_dir, "git"))

        preview = self.service.preview_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "remote-repo")
        self.assertEqual(self.backend.status_calls[0][1], "root-folder/remote-repo/feature-a")
