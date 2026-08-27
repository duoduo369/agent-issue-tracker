import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.pull_service import PullConfirmationRequired, PullService
from feishu_issue_tracker.sidecar import FeatureSidecar


@dataclass
class FakeStatusResult:
    new_local: list[str]
    modified: list[str]
    unchanged: list[str]
    new_remote: list[str]


class FakeFeishuClient:
    def __init__(self) -> None:
        self.ready_checks = 0
        self.status_calls: list[tuple[str, str]] = []
        self.pull_calls: list[tuple[str, str]] = []
        self.child_folders: dict[tuple[str, str], str] = {}
        self.status_result = FakeStatusResult(
            new_local=["map.md"],
            modified=["issues/01.md"],
            unchanged=["spec.md"],
            new_remote=["issues/02.md", "notes.txt"],
        )
        self.remote_files = {
            "spec.md": "# remote spec\n",
            "issues/01.md": "# remote issue 1\n",
            "issues/02.md": "# remote issue 2\n",
            "notes.txt": "remote extra\n",
        }

    def ensure_ready(self) -> None:
        self.ready_checks += 1

    def find_child_folder(self, parent_token: str, name: str) -> str | None:
        return self.child_folders.get((parent_token, name))

    def status(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> FakeStatusResult:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.status_calls.append((rel_local_dir, folder_token))
        return self.status_result

    def pull(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> dict:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.pull_calls.append((rel_local_dir, folder_token))
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
        self.sidecar_path = feature_dir / ".feishu-sync.json"
        self.client = FakeFeishuClient()
        self.client.child_folders[("root-folder", "remote-repo")] = "root-folder/remote-repo"
        self.client.child_folders[("root-folder/remote-repo", "feature-a")] = (
            "root-folder/remote-repo/feature-a"
        )
        self.service = PullService(
            layout_provider=ScratchLayoutProvider(),
            feishu_client=self.client,
        )
        self.config = ResolvedConfig(
            values={
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "root-folder",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "remote-repo",
            },
            sources={
                "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "env",
                "FEISHU_ISSUE_TRACKER_REPO_NAME": "env",
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
        self.assertEqual(self.client.status_calls[0][1], "root-folder/remote-repo/feature-a")

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

        self.assertEqual(self.client.ready_checks, 1)
        self.assertEqual(result.preview.remote_feature_folder_token, "root-folder/remote-repo/feature-a")
        self.assertEqual((self.feature_dir / "spec.md").read_text(encoding="utf-8"), "# remote spec\n")
        self.assertEqual(
            (self.feature_dir / "issues" / "02.md").read_text(encoding="utf-8"),
            "# remote issue 2\n",
        )
        self.assertFalse((self.feature_dir / "notes.txt").exists())
        sidecar = FeatureSidecar.load(self.sidecar_path)
        self.assertEqual(sidecar.remote_feature_folder_token, "root-folder/remote-repo/feature-a")
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
            feature_name="feature-a",
            resolved_repo_name="stable-repo",
            remote_root_folder_token="stable-root",
            remote_repo_folder_token="stable-root/stable-repo",
            remote_feature_folder_token="stable-root/stable-repo/feature-a",
        ).save(self.sidecar_path)

        preview = self.service.preview_pull(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "stable-repo")
        self.assertEqual(self.client.status_calls[0][1], "stable-root/stable-repo/feature-a")
