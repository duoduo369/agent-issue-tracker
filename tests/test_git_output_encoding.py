import subprocess
import tempfile
import unittest
from pathlib import Path

from feishu_issue_tracker.git_backend import GitPersistenceBackend


class GitOutputEncodingTests(unittest.TestCase):
    def test_utf8_git_output_is_decoded_independently_of_host_locale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            setup_commands = (
                ("init", "--quiet"),
                ("config", "user.name", "Codex Test"),
                ("config", "user.email", "codex@example.com"),
            )
            for args in setup_commands:
                subprocess.run(
                    ["git", *args],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                )

            expected = "Studio output: 📘\n"
            (repository / "fixture.txt").write_text(expected, encoding="utf-8")
            for args in (("add", "fixture.txt"), ("commit", "--quiet", "-m", "seed")):
                subprocess.run(
                    ["git", *args],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                )

            backend = GitPersistenceBackend(tracker_repo_path=repository)
            result = backend._run_git("show", "HEAD:fixture.txt")

            self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
