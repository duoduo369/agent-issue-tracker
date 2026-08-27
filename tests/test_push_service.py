import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from feishu_issue_tracker.config import ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.push_service import PushConfirmationRequired, PushService
from feishu_issue_tracker.sidecar import FeatureSidecar


@dataclass
class FakeStatusResult:
    local_only: list[str]
    modified: list[str]
    unchanged: list[str]
    remote_only: list[str]


class FakeFeishuClient:
    def __init__(self) -> None:
        self.ready_checks = 0
        self.status_calls: list[tuple[str, str]] = []
        self.push_calls: list[tuple[str, str]] = []
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

    def find_child_folder(self, parent_token: str, name: str) -> str | None:
        return self.child_folders.get((parent_token, name))

    def create_folder(self, parent_token: str, name: str) -> str:
        token = f"{parent_token}/{name}"
        self.created_folders.append((parent_token, name))
        self.child_folders[(parent_token, name)] = token
        return token

    def status(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> FakeStatusResult:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.status_calls.append((rel_local_dir, folder_token))
        return self.status_result

    def push(self, *, repo_root: Path, local_dir: Path, folder_token: str) -> dict:
        rel_local_dir = local_dir.relative_to(repo_root).as_posix()
        self.push_calls.append((rel_local_dir, folder_token))
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
        self.sidecar_path = feature_dir / ".feishu-sync.json"
        self.client = FakeFeishuClient()
        self.client.child_folders[("root-folder", "remote-repo")] = "root-folder/remote-repo"
        self.client.child_folders[("root-folder/remote-repo", "feature-a")] = (
            "root-folder/remote-repo/feature-a"
        )
        self.service = PushService(
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
        self.assertEqual(self.client.status_calls[0][1], "root-folder/remote-repo/feature-a")

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

        self.assertEqual(self.client.ready_checks, 1)
        self.assertEqual(result.preview.resolved_repo_name, "remote-repo")
        self.assertEqual(self.client.push_calls[0][1], "root-folder/remote-repo/feature-a")
        sidecar = FeatureSidecar.load(self.sidecar_path)
        self.assertEqual(sidecar.remote_feature_folder_token, "root-folder/remote-repo/feature-a")
        self.assertEqual(sidecar.resolved_repo_name, "remote-repo")

    def test_reuses_existing_sidecar_mapping(self) -> None:
        FeatureSidecar(
            feature_name="feature-a",
            resolved_repo_name="stable-repo",
            remote_root_folder_token="stable-root",
            remote_repo_folder_token="stable-root/stable-repo",
            remote_feature_folder_token="stable-root/stable-repo/feature-a",
        ).save(self.sidecar_path)

        preview = self.service.preview_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "stable-repo")
        self.assertEqual(self.client.status_calls[0][1], "stable-root/stable-repo/feature-a")

    def test_ignores_sidecar_mapping_when_feature_name_does_not_match(self) -> None:
        FeatureSidecar(
            feature_name="feature-b",
            resolved_repo_name="stable-repo",
            remote_root_folder_token="stable-root",
            remote_repo_folder_token="stable-root/stable-repo",
            remote_feature_folder_token="stable-root/stable-repo/feature-b",
        ).save(self.sidecar_path)

        preview = self.service.preview_push(
            repo_root=self.repo_root,
            cwd=self.feature_dir,
            feature_name=None,
            resolved_config=self.config,
        )

        self.assertEqual(preview.resolved_repo_name, "remote-repo")
        self.assertEqual(self.client.status_calls[0][1], "root-folder/remote-repo/feature-a")
