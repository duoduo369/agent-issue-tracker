import tempfile
import unittest
from pathlib import Path

from feishu_issue_tracker.layout import FeatureResolutionError, ScratchLayoutProvider


class ScratchLayoutProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        (self.repo_root / ".git").mkdir()
        self.feature_dir = self.repo_root / ".scratch" / "feature-a"
        (self.feature_dir / "issues").mkdir(parents=True)
        (self.feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
        (self.feature_dir / "map.md").write_text("# map\n", encoding="utf-8")
        (self.feature_dir / "issues" / "01.md").write_text("# issue\n", encoding="utf-8")
        (self.feature_dir / "notes.txt").write_text("local only\n", encoding="utf-8")
        (self.feature_dir / ".feishu-sync.json").write_text("{}", encoding="utf-8")
        self.provider = ScratchLayoutProvider()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_detects_feature_from_nested_scratch_directory(self) -> None:
        cwd = self.feature_dir / "issues"

        feature_name = self.provider.resolve_feature_name(
            repo_root=self.repo_root,
            cwd=cwd,
            explicit_feature=None,
        )

        self.assertEqual(feature_name, "feature-a")

    def test_requires_explicit_feature_outside_scratch(self) -> None:
        with self.assertRaises(FeatureResolutionError):
            self.provider.resolve_feature_name(
                repo_root=self.repo_root,
                cwd=self.repo_root,
                explicit_feature=None,
            )

    def test_rejects_explicit_feature_that_escapes_scratch_directory(self) -> None:
        with self.assertRaises(FeatureResolutionError):
            self.provider.resolve_feature_name(
                repo_root=self.repo_root,
                cwd=self.repo_root,
                explicit_feature="../outside",
            )

    def test_discovers_only_canonical_files(self) -> None:
        canonical_files = self.provider.collect_canonical_files(self.feature_dir)

        self.assertEqual(
            [item.rel_path for item in canonical_files],
            ["issues/01.md", "map.md", "spec.md"],
        )

    def test_lists_non_canonical_local_files_and_ignores_sidecar(self) -> None:
        extra_files = self.provider.collect_local_extra_files(self.feature_dir)

        self.assertEqual(extra_files, ["notes.txt"])

    def test_maps_canonical_issue_file_to_restore_destination(self) -> None:
        destination = self.provider.restore_destination(
            self.feature_dir,
            "issues/02.md",
        )

        self.assertEqual(destination, self.feature_dir / "issues" / "02.md")
