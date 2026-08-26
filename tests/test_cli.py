import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from feishu_issue_tracker.cli import main


class CliTests(unittest.TestCase):
    def test_config_write_persists_values(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "config",
                        "write",
                        "--root-folder-token",
                        "root-folder",
                        "--repo-name",
                        "remote-repo",
                        "--path",
                        str(config_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                {
                    "FEISHU_ISSUE_TRACKER_REPO_NAME": "remote-repo",
                    "FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": "root-folder",
                },
            )

    def test_push_reports_missing_config_before_running(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / ".git").mkdir()
            stdout = StringIO()
            original_cwd = Path.cwd()
            try:
                os.chdir(repo_root)
                with redirect_stdout(stdout):
                    exit_code = main(["push", "--feature", "feature-a"])
            finally:
                os.chdir(original_cwd)

            self.assertEqual(exit_code, 2)
