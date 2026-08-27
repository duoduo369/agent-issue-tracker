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
from feishu_issue_tracker.pull_service import PullConfirmationRequired, PullService
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
        self.pull_calls: list[tuple[str, str]] = []
        self.child_folders: dict[tuple[str, str], str] = {}
        self.status_result = FakeStatusResult(
            local_only=["map.md"],
            modified=["issues/01.md"],
            unchanged=["spec.md"],
            remote_only=["issues/02.md", "notes.txt"],
        )
        self.remote_files = {
            "spec.md": "# remote spec\n",
            "issues/01.md": "# remote issue 1\n",
            "issues/02.md": "# remote issue 2\n",
            "notes.txt": "remote extra\n",
        }

    def ensure_ready(self) -> None:
        self.ready_checks += 1

    def root_locator_from_config(self, *, resolved_config: ResolvedConfig) -> str:
        return resolved_config.values[FEISHU_ROOT_FOLDER_TOKEN_KEY]

    def find_remote_repo(self, *, root_locator: str, repo_name: str) -> str | None:
        return self.child_folders.get((root_locator, repo_name))

    def find_remote_feature(self, *, repo_locator: str, feature_name: str) -> str | None:
        return self.child_folders.get((repo_locator, feature_name))

    def status(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> FakeStatusResult:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.status_calls.append((rel_local_dir, remote_locator))
        return self.status_result

    def pull(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> dict:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.pull_calls.append((rel_local_dir, remote_locator))
        for rel_path, content in self.remote_files.items():
            destination = local_dir / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        return {
            "summary": {
                "downloaded": 3,
                "skipped": 1,
                "failed": 0,
                "deleted_local": 0,
                "aborted": False,
            }
        }


class PullServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        (self.repo_root / ".git").mkdir()
        feature_dir = self.repo_root / ".scratch" / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# local spec\n", encoding="utf-8")
        (feature_dir / "map.md").write_text("# local map\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# local issue 1\n", encoding="utf-8")
        (feature_dir / "draft.txt").write_text("scratch note\n", encoding="utf-8")
        self.feature_dir = feature_dir
        self.sidecar_path = sidecar_path(feature_dir, "feishu")
        self.backend = FakeBackend()
        self.backend.child_folders[("root-folder", "remote-repo")] = "root-folder/remote-repo"
        self.backend.child_folders[("root-folder/remote-repo", "feature-a")] = (
            "root-folder/remote-repo/feature-a"
        )
        self.service = PullService(
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

    def test_preview_classifies_remote_canonical_and_extra_files(self) -> None:
        preview = self.service.preview_pull(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.feature_name, "feature-a")
        self.assertEqual(preview.will_create, ["issues/02.md"])
        self.assertEqual(preview.will_overwrite, ["issues/01.md"])
        self.assertEqual(preview.local_only_canonical, ["map.md"])
        self.assertEqual(preview.remote_extra_files, ["notes.txt"])
        self.assertEqual(preview.local_extra_files, ["draft.txt"])
        self.assertTrue(preview.confirmation_required)
        self.assertEqual(preview.backend_name, "feishu")
        self.assertEqual(preview.tracker_feature_locator, "root-folder/remote-repo/feature-a")
        self.assertEqual(self.backend.status_calls[0][1], "root-folder/remote-repo/feature-a")

    def test_execute_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(PullConfirmationRequired):
            self.service.execute_pull(
                repo_root=self.repo_root,
                cwd=self.feature_dir,
                feature_name=None,
                resolved_config=self.config,
                confirm=False,
            )

    def test_execute_restores_canonical_files_for_missing_feature_dir_and_updates_sidecar(self) -> None:
        for path in sorted(self.feature_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        self.feature_dir.rmdir()

        result = self.service.execute_pull(
            repo_root=self.repo_root,
            cwd=self.repo_root,
            feature_name="feature-a",
            resolved_config=self.config,
            confirm=True,
        )

        self.assertEqual(self.backend.ready_checks, 1)
        self.assertEqual(result.preview.tracker_feature_locator, "root-folder/remote-repo/feature-a")
        self.assertEqual((self.feature_dir / "spec.md").read_text(encoding="utf-8"), "# remote spec\n")
        self.assertEqual(
            (self.feature_dir / "issues" / "02.md").read_text(encoding="utf-8"),
            "# remote issue 2\n",
        )
        self.assertFalse((self.feature_dir / "notes.txt").exists())
        sidecar = FeatureSidecar.load(self.sidecar_path)
        self.assertEqual(sidecar.backend_name, "feishu")
        self.assertEqual(sidecar.feature_locator, "root-folder/remote-repo/feature-a")
        self.assertEqual(sidecar.resolved_repo_name, "remote-repo")

    def test_execute_removes_local_only_canonical_files(self) -> None:
        result = self.service.execute_pull(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
            confirm=True,
        )

        self.assertEqual(result.preview.local_only_canonical, ["map.md"])
        self.assertFalse((self.feature_dir / "map.md").exists())
        self.assertEqual((self.feature_dir / "spec.md").read_text(encoding="utf-8"), "# remote spec\n")

    def test_reuses_existing_sidecar_mapping(self) -> None:
        FeatureSidecar(
            backend_name="feishu",
            feature_name="feature-a",
            resolved_repo_name="stable-repo",
            root_locator="stable-root",
            repo_locator="stable-root/stable-repo",
            feature_locator="stable-root/stable-repo/feature-a",
        ).save(self.sidecar_path)

        preview = self.service.preview_pull(
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

        preview = self.service.preview_pull(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "remote-repo")
        self.assertEqual(self.backend.status_calls[0][1], "root-folder/remote-repo/feature-a")
