import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from feishu_issue_tracker.backend import PersistenceBackendError
from feishu_issue_tracker.config import GIT_REPO_PATH_KEY, ResolvedConfig
from feishu_issue_tracker.layout import ScratchLayoutProvider
from feishu_issue_tracker.pull_service import PullService
from feishu_issue_tracker.push_service import PushService
from feishu_issue_tracker.sidecar import FeatureSidecar, sidecar_path


def _git(
    repo: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "Codex Test")
    env.setdefault("GIT_AUTHOR_EMAIL", "codex@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "Codex Test")
    env.setdefault("GIT_COMMITTER_EMAIL", "codex@example.com")
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


class GitPersistenceBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source_repo = self.root / "source-repo"
        self.source_repo.mkdir()
        (self.source_repo / ".git").mkdir()
        self.remote_repo = self.root / "tracker-remote.git"
        self.remote_repo.mkdir()
        _git(self.remote_repo, "init", "--bare")

        self.tracker_workspace = self.root / "tracker-workspace"
        _git(self.root, "clone", str(self.remote_repo), str(self.tracker_workspace))
        (self.tracker_workspace / ".gitkeep").write_text("seed\n", encoding="utf-8")
        _git(self.tracker_workspace, "add", ".gitkeep")
        _git(self.tracker_workspace, "commit", "-m", "seed tracker workspace")
        _git(self.tracker_workspace, "push", "-u", "origin", "HEAD")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_ensure_ready_requires_configured_remote(self) -> None:
        local_only_workspace = self.root / "local-only-workspace"
        local_only_workspace.mkdir()
        _git(local_only_workspace, "init")

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(tracker_repo_path=local_only_workspace)

        with self.assertRaises(PersistenceBackendError) as exc_info:
            backend.ensure_ready()

        self.assertIn("remote", str(exc_info.exception).lower())

    def test_ensure_ready_switches_to_configured_branch(self) -> None:
        current_branch = _git(self.tracker_workspace, "branch", "--show-current").stdout.strip()
        _git(self.tracker_workspace, "checkout", "-b", "issue-sync")
        _git(self.tracker_workspace, "push", "-u", "origin", "issue-sync")
        _git(self.tracker_workspace, "checkout", current_branch)

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(
            tracker_repo_path=self.tracker_workspace,
            branch="issue-sync",
        )
        backend.ensure_ready()

        self.assertEqual(
            _git(self.tracker_workspace, "branch", "--show-current").stdout.strip(),
            "issue-sync",
        )

    def test_status_classifies_canonical_and_extra_files(self) -> None:
        feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# remote spec\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# same issue\n", encoding="utf-8")
        (feature_dir / "issues" / "02.md").write_text("# remote only\n", encoding="utf-8")
        (feature_dir / "notes.txt").write_text("remote extra\n", encoding="utf-8")

        staging_dir = self.root / "staging"
        (staging_dir / "issues").mkdir(parents=True)
        (staging_dir / "spec.md").write_text("# local spec\n", encoding="utf-8")
        (staging_dir / "map.md").write_text("# local map\n", encoding="utf-8")
        (staging_dir / "issues" / "01.md").write_text("# same issue\n", encoding="utf-8")

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(tracker_repo_path=self.tracker_workspace)
        status = backend.status(
            repo_root=self.source_repo,
            local_dir=staging_dir,
            remote_locator=str(feature_dir),
        )

        self.assertEqual(status.local_only, ["map.md"])
        self.assertEqual(status.modified, ["spec.md"])
        self.assertEqual(status.unchanged, ["issues/01.md"])
        self.assertEqual(status.remote_only, ["issues/02.md", "notes.txt"])

    def test_push_copies_bundle_commits_and_pushes(self) -> None:
        feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        feature_dir.mkdir(parents=True)
        (feature_dir / "notes.txt").write_text("keep me\n", encoding="utf-8")
        _git(self.tracker_workspace, "add", ".")
        _git(self.tracker_workspace, "commit", "-m", "add tracker files")
        _git(self.tracker_workspace, "push")

        staging_dir = self.root / "push-staging"
        (staging_dir / "issues").mkdir(parents=True)
        (staging_dir / "spec.md").write_text("# pushed spec\n", encoding="utf-8")
        (staging_dir / "issues" / "01.md").write_text("# pushed issue\n", encoding="utf-8")

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(tracker_repo_path=self.tracker_workspace)
        result = backend.push(
            repo_root=self.source_repo,
            local_dir=staging_dir,
            remote_locator=str(feature_dir),
        )

        self.assertEqual((feature_dir / "spec.md").read_text(encoding="utf-8"), "# pushed spec\n")
        self.assertEqual(
            (feature_dir / "issues" / "01.md").read_text(encoding="utf-8"),
            "# pushed issue\n",
        )
        self.assertEqual((feature_dir / "notes.txt").read_text(encoding="utf-8"), "keep me\n")
        self.assertTrue(result["summary"]["committed"])
        self.assertTrue(result["summary"]["pushed"])
        self.assertFalse(result["summary"]["rebase_attempted"])

        verification_clone = self.root / "verification-clone"
        _git(self.root, "clone", str(self.remote_repo), str(verification_clone))
        pushed_feature_dir = verification_clone / self.source_repo.name / "feature-a"
        self.assertTrue((pushed_feature_dir / "spec.md").exists())

    def test_delete_remote_paths_removes_requested_canonical_files(self) -> None:
        feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "issues" / "stale.md").write_text("# stale\n", encoding="utf-8")
        (feature_dir / "notes.txt").write_text("keep me\n", encoding="utf-8")

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(tracker_repo_path=self.tracker_workspace)
        deleted = backend.delete_remote_paths(
            remote_locator=str(feature_dir),
            rel_paths=["issues/stale.md"],
        )

        self.assertEqual(deleted, 1)
        self.assertFalse((feature_dir / "issues" / "stale.md").exists())
        self.assertEqual((feature_dir / "notes.txt").read_text(encoding="utf-8"), "keep me\n")

    def test_push_retries_after_rebase_when_remote_moves_first(self) -> None:
        collaborator = self.root / "collaborator"
        _git(self.root, "clone", str(self.remote_repo), str(collaborator))
        (collaborator / "remote.txt").write_text("new remote commit\n", encoding="utf-8")
        _git(collaborator, "add", "remote.txt")
        _git(collaborator, "commit", "-m", "remote drift")
        _git(collaborator, "push")

        feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        staging_dir = self.root / "retry-staging"
        (staging_dir / "issues").mkdir(parents=True)
        (staging_dir / "spec.md").write_text("# retry spec\n", encoding="utf-8")
        (staging_dir / "issues" / "01.md").write_text("# retry issue\n", encoding="utf-8")

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(tracker_repo_path=self.tracker_workspace)
        result = backend.push(
            repo_root=self.source_repo,
            local_dir=staging_dir,
            remote_locator=str(feature_dir),
        )

        self.assertTrue(result["summary"]["rebase_attempted"])
        self.assertEqual(result["summary"]["push_attempts"], 2)

        verification_clone = self.root / "verification-after-retry"
        _git(self.root, "clone", str(self.remote_repo), str(verification_clone))
        self.assertEqual(
            (verification_clone / "remote.txt").read_text(encoding="utf-8"),
            "new remote commit\n",
        )
        self.assertEqual(
            (
                verification_clone / self.source_repo.name / "feature-a" / "spec.md"
            ).read_text(encoding="utf-8"),
            "# retry spec\n",
        )

    def test_pull_updates_tracker_workspace_before_copying_remote_bundle(self) -> None:
        collaborator = self.root / "pull-collaborator"
        _git(self.root, "clone", str(self.remote_repo), str(collaborator))
        feature_dir = collaborator / self.source_repo.name / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# remote spec\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# remote issue\n", encoding="utf-8")
        (feature_dir / "notes.txt").write_text("remote extra\n", encoding="utf-8")
        _git(collaborator, "add", ".")
        _git(collaborator, "commit", "-m", "publish remote bundle")
        _git(collaborator, "push")

        staging_dir = self.root / "pull-staging"
        staging_dir.mkdir()

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        backend = GitPersistenceBackend(tracker_repo_path=self.tracker_workspace)
        result = backend.pull(
            repo_root=self.source_repo,
            local_dir=staging_dir,
            remote_locator=str(self.tracker_workspace / self.source_repo.name / "feature-a"),
        )

        self.assertEqual((staging_dir / "spec.md").read_text(encoding="utf-8"), "# remote spec\n")
        self.assertEqual(
            (staging_dir / "issues" / "01.md").read_text(encoding="utf-8"),
            "# remote issue\n",
        )
        self.assertTrue(result["summary"]["updated_workspace"])

    def test_push_service_preview_matches_common_semantics_for_git_backend(self) -> None:
        feature_dir = self.source_repo / ".scratch" / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# local spec\n", encoding="utf-8")
        (feature_dir / "map.md").write_text("# local map\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# shared issue\n", encoding="utf-8")
        (feature_dir / "draft.txt").write_text("local extra\n", encoding="utf-8")
        tracker_feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        (tracker_feature_dir / "issues").mkdir(parents=True)
        (tracker_feature_dir / "spec.md").write_text("# remote spec\n", encoding="utf-8")
        (tracker_feature_dir / "issues" / "01.md").write_text("# shared issue\n", encoding="utf-8")
        (tracker_feature_dir / "issues" / "02.md").write_text("# remote only\n", encoding="utf-8")
        (tracker_feature_dir / "notes.txt").write_text("remote extra\n", encoding="utf-8")

        FeatureSidecar(
            backend_name="feishu",
            feature_name="feature-a",
            resolved_repo_name="wrong-repo",
            root_locator="wrong-root",
            repo_locator="wrong-root/wrong-repo",
            feature_locator="wrong-root/wrong-repo/feature-a",
        ).save(feature_dir / ".issue-tracker.feishu.json")

        resolved_config = ResolvedConfig(
            backend="git",
            values={GIT_REPO_PATH_KEY: str(self.tracker_workspace)},
            sources={GIT_REPO_PATH_KEY: "env"},
            missing_keys=[],
        )

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        preview = PushService(
            layout_provider=ScratchLayoutProvider(),
            backend=GitPersistenceBackend(tracker_repo_path=self.tracker_workspace),
        ).preview_push(
            repo_root=self.source_repo,
            cwd=feature_dir,
            feature_name=None,
            resolved_config=resolved_config,
        )

        self.assertEqual(preview.backend_name, "git")
        self.assertEqual(preview.tracker_root_locator, str(self.tracker_workspace))
        self.assertNotEqual(preview.tracker_root_locator, "wrong-root")
        self.assertEqual(preview.will_create, ["map.md"])
        self.assertEqual(preview.will_overwrite, ["spec.md"])
        self.assertEqual(preview.unchanged, ["issues/01.md"])
        self.assertEqual(preview.remote_only_canonical, ["issues/02.md"])
        self.assertEqual(preview.remote_extra_files, ["notes.txt"])
        self.assertEqual(preview.local_extra_files, ["draft.txt"])
        self.assertTrue(preview.confirmation_required)

    def test_execute_push_deletes_remote_only_canonical_and_writes_git_sidecar(self) -> None:
        feature_dir = self.source_repo / ".scratch" / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# local spec\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# local issue\n", encoding="utf-8")

        tracker_feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        (tracker_feature_dir / "issues").mkdir(parents=True)
        (tracker_feature_dir / "issues" / "stale.md").write_text("# stale\n", encoding="utf-8")
        (tracker_feature_dir / "notes.txt").write_text("keep me\n", encoding="utf-8")
        _git(self.tracker_workspace, "add", ".")
        _git(self.tracker_workspace, "commit", "-m", "seed tracker feature")
        _git(self.tracker_workspace, "push")

        resolved_config = ResolvedConfig(
            backend="git",
            values={GIT_REPO_PATH_KEY: str(self.tracker_workspace)},
            sources={GIT_REPO_PATH_KEY: "env"},
            missing_keys=[],
        )

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        result = PushService(
            layout_provider=ScratchLayoutProvider(),
            backend=GitPersistenceBackend(tracker_repo_path=self.tracker_workspace),
        ).execute_push(
            repo_root=self.source_repo,
            cwd=feature_dir,
            feature_name=None,
            resolved_config=resolved_config,
            confirm=True,
        )

        self.assertEqual(result.push_result["summary"]["deleted_remote"], 1)
        self.assertFalse((tracker_feature_dir / "issues" / "stale.md").exists())
        self.assertEqual((tracker_feature_dir / "notes.txt").read_text(encoding="utf-8"), "keep me\n")
        sidecar = FeatureSidecar.load(sidecar_path(feature_dir, "git"))
        self.assertEqual(sidecar.backend_name, "git")
        self.assertEqual(sidecar.root_locator, str(self.tracker_workspace))

    def test_pull_service_preview_reports_overwrite_direction_for_git_backend(self) -> None:
        feature_dir = self.source_repo / ".scratch" / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# local spec\n", encoding="utf-8")
        (feature_dir / "map.md").write_text("# local map\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# local issue\n", encoding="utf-8")
        (feature_dir / "draft.txt").write_text("local extra\n", encoding="utf-8")

        local_tracker_feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        (local_tracker_feature_dir / "issues").mkdir(parents=True)
        (local_tracker_feature_dir / "spec.md").write_text("# stale spec\n", encoding="utf-8")
        (local_tracker_feature_dir / "issues" / "01.md").write_text("# stale issue\n", encoding="utf-8")
        _git(self.tracker_workspace, "add", ".")
        _git(self.tracker_workspace, "commit", "-m", "seed stale tracker state")
        _git(self.tracker_workspace, "push")

        collaborator = self.root / "preview-collaborator"
        _git(self.root, "clone", str(self.remote_repo), str(collaborator))
        tracker_feature_dir = collaborator / self.source_repo.name / "feature-a"
        (tracker_feature_dir / "issues").mkdir(parents=True, exist_ok=True)
        (tracker_feature_dir / "spec.md").write_text("# remote spec\n", encoding="utf-8")
        (tracker_feature_dir / "issues" / "01.md").write_text("# remote issue\n", encoding="utf-8")
        (tracker_feature_dir / "issues" / "02.md").write_text("# remote new issue\n", encoding="utf-8")
        (tracker_feature_dir / "notes.txt").write_text("remote extra\n", encoding="utf-8")
        _git(collaborator, "add", ".")
        _git(collaborator, "commit", "-m", "publish preview state")
        _git(collaborator, "push")

        resolved_config = ResolvedConfig(
            backend="git",
            values={GIT_REPO_PATH_KEY: str(self.tracker_workspace)},
            sources={GIT_REPO_PATH_KEY: "env"},
            missing_keys=[],
        )

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        preview = PullService(
            layout_provider=ScratchLayoutProvider(),
            backend=GitPersistenceBackend(tracker_repo_path=self.tracker_workspace),
        ).preview_pull(
            repo_root=self.source_repo,
            cwd=feature_dir,
            feature_name=None,
            resolved_config=resolved_config,
        )

        self.assertEqual(preview.will_create, ["issues/02.md"])
        self.assertEqual(preview.will_overwrite, ["issues/01.md", "spec.md"])
        self.assertEqual(preview.local_only_canonical, ["map.md"])
        self.assertEqual(preview.remote_extra_files, ["notes.txt"])
        self.assertEqual(preview.local_extra_files, ["draft.txt"])
        self.assertIn("source of truth", preview.overwrite_hint)
        self.assertTrue(preview.confirmation_required)
        self.assertEqual(
            (self.tracker_workspace / self.source_repo.name / "feature-a" / "issues" / "02.md").read_text(
                encoding="utf-8"
            ),
            "# remote new issue\n",
        )

    def test_execute_pull_restores_only_canonical_files_from_git_backend(self) -> None:
        feature_dir = self.source_repo / ".scratch" / "feature-a"
        (feature_dir / "issues").mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# local spec\n", encoding="utf-8")
        (feature_dir / "map.md").write_text("# local map\n", encoding="utf-8")
        (feature_dir / "issues" / "01.md").write_text("# local issue\n", encoding="utf-8")
        (feature_dir / "draft.txt").write_text("local extra\n", encoding="utf-8")

        local_tracker_feature_dir = self.tracker_workspace / self.source_repo.name / "feature-a"
        (local_tracker_feature_dir / "issues").mkdir(parents=True)
        (local_tracker_feature_dir / "spec.md").write_text("# stale spec\n", encoding="utf-8")
        (local_tracker_feature_dir / "issues" / "01.md").write_text("# stale issue\n", encoding="utf-8")
        _git(self.tracker_workspace, "add", ".")
        _git(self.tracker_workspace, "commit", "-m", "seed local tracker feature")
        _git(self.tracker_workspace, "push")

        collaborator = self.root / "pull-collaborator"
        _git(self.root, "clone", str(self.remote_repo), str(collaborator))
        tracker_feature_dir = collaborator / self.source_repo.name / "feature-a"
        (tracker_feature_dir / "issues").mkdir(parents=True, exist_ok=True)
        (tracker_feature_dir / "spec.md").write_text("# remote spec\n", encoding="utf-8")
        (tracker_feature_dir / "issues" / "01.md").write_text("# remote issue\n", encoding="utf-8")
        (tracker_feature_dir / "issues" / "02.md").write_text("# remote new issue\n", encoding="utf-8")
        (tracker_feature_dir / "notes.txt").write_text("remote extra\n", encoding="utf-8")
        _git(collaborator, "add", ".")
        _git(collaborator, "commit", "-m", "publish remote pull state")
        _git(collaborator, "push")

        resolved_config = ResolvedConfig(
            backend="git",
            values={GIT_REPO_PATH_KEY: str(self.tracker_workspace)},
            sources={GIT_REPO_PATH_KEY: "env"},
            missing_keys=[],
        )

        from feishu_issue_tracker.git_backend import GitPersistenceBackend

        result = PullService(
            layout_provider=ScratchLayoutProvider(),
            backend=GitPersistenceBackend(tracker_repo_path=self.tracker_workspace),
        ).execute_pull(
            repo_root=self.source_repo,
            cwd=feature_dir,
            feature_name=None,
            resolved_config=resolved_config,
            confirm=True,
        )

        self.assertIn("source of truth", result.preview.overwrite_hint)
        self.assertEqual((feature_dir / "spec.md").read_text(encoding="utf-8"), "# remote spec\n")
        self.assertEqual(
            (feature_dir / "issues" / "02.md").read_text(encoding="utf-8"),
            "# remote new issue\n",
        )
        self.assertFalse((feature_dir / "map.md").exists())
        self.assertFalse((feature_dir / "notes.txt").exists())


class GitCliDispatchTests(unittest.TestCase):
    def test_git_backend_preview_uses_actual_backend_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "source-repo"
            repo_root.mkdir(parents=True)
            (repo_root / ".git").mkdir()
            feature_dir = repo_root / ".scratch" / "feature-a"
            (feature_dir / "issues").mkdir(parents=True)
            (feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")

            tracker_workspace = Path(tempdir) / "tracker-workspace"
            tracker_workspace.mkdir()
            (repo_root / ".env").write_text(
                "AGENT_ISSUE_TRACKER_BACKEND=git\n"
                f"AGENT_ISSUE_TRACKER_GIT_REPO_PATH={tracker_workspace}\n",
                encoding="utf-8",
            )

            from contextlib import redirect_stdout
            from io import StringIO

            from feishu_issue_tracker.cli import main

            stdout = StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with redirect_stdout(stdout):
                    exit_code = main(["push", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 0)
            payload = stdout.getvalue()
            self.assertIn('"backend": "git"', payload)
            self.assertIn('"mode": "preview"', payload)
