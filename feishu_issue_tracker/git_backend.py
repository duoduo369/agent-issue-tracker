from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from feishu_issue_tracker.backend import PersistenceBackendError, SyncStatus
from feishu_issue_tracker.config import GIT_REPO_PATH_KEY, ResolvedConfig


class GitPersistenceBackend:
    backend_name = "git"

    def __init__(
        self,
        *,
        tracker_repo_path: Path,
        branch: str | None = None,
        git_bin: str = "git",
    ) -> None:
        self.tracker_repo_path = Path(tracker_repo_path)
        self.branch = branch.strip() if branch and branch.strip() else None
        self.git_bin = git_bin

    def ensure_ready(self) -> None:
        if not self.tracker_repo_path.exists():
            raise PersistenceBackendError(
                f"Git tracker workspace {self.tracker_repo_path} does not exist.",
                status="missing_workspace",
            )
        self._run_git(
            "rev-parse",
            "--is-inside-work-tree",
            status="missing_workspace",
            hint="Set AGENT_ISSUE_TRACKER_GIT_REPO_PATH to an existing local Git checkout.",
        )
        self._ensure_selected_branch()
        self._ensure_tracking_branch()

    def prepare_pull_preview(self) -> None:
        self.ensure_ready()
        self._pull_rebase(strategy_option="ours")

    def root_locator_from_config(self, *, resolved_config: ResolvedConfig) -> str:
        return str(Path(resolved_config.values[GIT_REPO_PATH_KEY]))

    def find_remote_repo(self, *, root_locator: str, repo_name: str) -> str | None:
        candidate = Path(root_locator) / repo_name
        return str(candidate) if candidate.exists() else None

    def find_remote_feature(self, *, repo_locator: str, feature_name: str) -> str | None:
        candidate = Path(repo_locator) / feature_name
        return str(candidate) if candidate.exists() else None

    def create_remote_repo(self, *, root_locator: str, repo_name: str) -> str:
        candidate = Path(root_locator) / repo_name
        candidate.mkdir(parents=True, exist_ok=True)
        return str(candidate)

    def create_remote_feature(self, *, repo_locator: str, feature_name: str) -> str:
        candidate = Path(repo_locator) / feature_name
        candidate.mkdir(parents=True, exist_ok=True)
        return str(candidate)

    def delete_remote_paths(self, *, remote_locator: str, rel_paths: list[str]) -> int:
        remote_dir = Path(remote_locator)
        deleted = 0
        for rel_path in rel_paths:
            candidate = remote_dir / rel_path
            if candidate.exists():
                self._delete_path(candidate, stop_at=remote_dir)
                deleted += 1
        return deleted

    def status(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> SyncStatus:
        del repo_root
        local_files = self._collect_files(local_dir)
        remote_dir = Path(remote_locator)
        remote_files = self._collect_files(remote_dir) if remote_dir.exists() else {}

        local_only: list[str] = []
        modified: list[str] = []
        unchanged: list[str] = []
        remote_only: list[str] = []
        for rel_path in sorted(set(local_files) | set(remote_files)):
            local_path = local_files.get(rel_path)
            remote_path = remote_files.get(rel_path)
            if local_path is None:
                remote_only.append(rel_path)
            elif remote_path is None:
                local_only.append(rel_path)
            elif local_path.read_bytes() == remote_path.read_bytes():
                unchanged.append(rel_path)
            else:
                modified.append(rel_path)
        return SyncStatus(
            local_only=local_only,
            modified=modified,
            unchanged=unchanged,
            remote_only=remote_only,
        )

    def push(self, *, repo_root: Path, local_dir: Path, remote_locator: str) -> dict:
        del repo_root
        self.ensure_ready()

        remote_dir = Path(remote_locator)
        remote_dir.mkdir(parents=True, exist_ok=True)
        copy_summary = self._sync_remote_tree(local_dir=local_dir, remote_dir=remote_dir)
        pathspec = self._pathspec_for(remote_dir)
        committed = self._commit_if_needed(pathspec=pathspec)

        rebase_attempted = False
        push_attempts = 0
        pushed = False
        if committed:
            try:
                push_attempts += 1
                self._run_git("push")
                pushed = True
            except PersistenceBackendError:
                rebase_attempted = True
                self._pull_rebase(strategy_option="theirs")
                retry_summary = self._sync_remote_tree(local_dir=local_dir, remote_dir=remote_dir)
                copy_summary["copied"] = retry_summary["copied"]
                committed = self._commit_if_needed(pathspec=pathspec) or committed
                push_attempts += 1
                self._run_git("push")
                pushed = True

        return {
            "summary": {
                "copied": copy_summary["copied"],
                "committed": committed,
                "pushed": pushed,
                "rebase_attempted": rebase_attempted,
                "push_attempts": push_attempts,
            }
        }

    def pull(
        self,
        *,
        repo_root: Path,
        local_dir: Path,
        remote_locator: str,
        refresh: bool = True,
    ) -> dict:
        del repo_root
        if refresh:
            self.prepare_pull_preview()
        else:
            self.ensure_ready()

        remote_dir = Path(remote_locator)
        if not remote_dir.exists():
            raise PersistenceBackendError(
                f"Git tracker workspace feature {remote_dir} does not exist.",
                status="missing_feature",
            )

        self._replace_tree(destination=local_dir, source=remote_dir)
        return {
            "summary": {
                "restored_files": len(self._collect_files(local_dir)),
                "updated_workspace": True,
            }
        }

    def _sync_remote_tree(self, *, local_dir: Path, remote_dir: Path) -> dict[str, int]:
        local_files = self._collect_files(local_dir)

        copied = 0
        for rel_path, source in local_files.items():
            destination = remote_dir / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or destination.read_bytes() != source.read_bytes():
                shutil.copy2(source, destination)
                copied += 1

        return {"copied": copied}

    def _commit_if_needed(self, *, pathspec: str) -> bool:
        self._run_git("add", "-A", "--", pathspec)
        diff_result = self._run_git(
            "diff",
            "--cached",
            "--quiet",
            "--",
            pathspec,
            check=False,
        )
        if diff_result.returncode == 0:
            return False
        if diff_result.returncode != 1:
            raise PersistenceBackendError(
                f"Could not inspect staged Git changes for {pathspec}.",
                status="command_error",
            )

        self._run_git("commit", "-m", f"issue-tracker: sync {pathspec}")
        return True

    def _pull_rebase(self, *, strategy_option: str) -> None:
        self._run_git("pull", "--rebase", "-X", strategy_option)

    def _ensure_selected_branch(self) -> None:
        if self.branch is None:
            return

        current_branch = self._current_branch_name()
        if current_branch == self.branch:
            return

        local_branch = self._run_git(
            "show-ref",
            "--verify",
            f"refs/heads/{self.branch}",
            check=False,
        )
        if local_branch.returncode == 0:
            self._run_git("checkout", self.branch)
            return

        remote_branch = self._run_git(
            "ls-remote",
            "--exit-code",
            "--heads",
            "origin",
            self.branch,
            check=False,
        )
        if remote_branch.returncode == 0:
            self._run_git("fetch", "origin", self.branch)
            self._run_git("checkout", "-b", self.branch, "--track", f"origin/{self.branch}")
            return

        raise PersistenceBackendError(
            f"Configured Git branch {self.branch!r} does not exist on origin.",
            status="missing_branch",
            hint=(
                "Set AGENT_ISSUE_TRACKER_GIT_BRANCH to an existing remote branch, "
                "or unset it to use the tracker workspace's current branch."
            ),
            recommended_command=f"{self.git_bin} ls-remote --heads origin {self.branch}",
        )

    def _ensure_tracking_branch(self) -> None:
        upstream = self._run_git(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
            check=False,
        )
        if upstream.returncode == 0:
            return

        branch_name = self._current_branch_name()
        if branch_name != "HEAD":
            remote_branch = self._run_git(
                "ls-remote",
                "--exit-code",
                "--heads",
                "origin",
                branch_name,
                check=False,
            )
            if remote_branch.returncode == 0:
                self._run_git("fetch", "origin", branch_name)
                self._run_git("branch", "--set-upstream-to", f"origin/{branch_name}", branch_name)
                retry = self._run_git(
                    "rev-parse",
                    "--abbrev-ref",
                    "--symbolic-full-name",
                    "@{u}",
                    check=False,
                )
                if retry.returncode == 0:
                    return

        raise PersistenceBackendError(
            "Git tracker workspace requires a configured remote tracking branch.",
            status="missing_remote",
            hint=(
                "The Git backend requires the selected tracker workspace branch "
                "to track a remote branch."
            ),
            recommended_command=(
                f"{self.git_bin} branch --set-upstream-to origin/{branch_name} {branch_name}"
                if branch_name != "HEAD"
                else None
            ),
        )

    def _replace_tree(self, *, destination: Path, source: Path) -> None:
        if destination.exists():
            for child in sorted(destination.iterdir(), reverse=True):
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        for item in sorted(source.rglob("*")):
            relative = item.relative_to(source)
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)

    def _pathspec_for(self, path: Path) -> str:
        return path.relative_to(self.tracker_repo_path).as_posix()

    def _current_branch_name(self) -> str:
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip()

    def _run_git(
        self,
        *args: str,
        check: bool = True,
        status: str = "command_error",
        hint: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [self.git_bin, *args],
            cwd=self.tracker_repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if not check or completed.returncode == 0:
            return completed

        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or "Git command failed."
        raise PersistenceBackendError(
            detail,
            status=status,
            hint=hint,
            recommended_command=f"{self.git_bin} {' '.join(args)}",
        )

    def _collect_files(self, root: Path) -> dict[str, Path]:
        if not root.exists():
            return {}
        files: dict[str, Path] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path
        return files

    def _delete_path(self, path: Path, *, stop_at: Path) -> None:
        path.unlink()
        self._prune_empty_parents(path.parent, stop_at=stop_at)

    def _prune_empty_parents(self, directory: Path, *, stop_at: Path) -> None:
        current = directory
        while current != stop_at and current.exists() and not any(current.iterdir()):
            current.rmdir()
            current = current.parent
