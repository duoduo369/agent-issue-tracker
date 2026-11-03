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
        (self.feature_dir / "maps").mkdir(parents=True)
        (self.feature_dir / "tickets").mkdir(parents=True)
        (self.feature_dir / "research").mkdir(parents=True)
        (self.feature_dir / "handoffs").mkdir(parents=True)
        (self.feature_dir / "spec.md").write_text("# spec\n", encoding="utf-8")
        (self.feature_dir / "map.md").write_text("# map\n", encoding="utf-8")
        (self.feature_dir / "README.md").write_text("# tracker readme\n", encoding="utf-8")
        (self.feature_dir / "CONTEXT.md").write_text("# context\n", encoding="utf-8")
        (self.feature_dir / "issues" / "01.md").write_text("# issue\n", encoding="utf-8")
        (self.feature_dir / "maps" / "wf-map.md").write_text("# wf map\n", encoding="utf-8")
        (self.feature_dir / "tickets" / "wf-001.md").write_text("# wf ticket\n", encoding="utf-8")
        (self.feature_dir / "research" / "facts.md").write_text("# facts\n", encoding="utf-8")
        (self.feature_dir / "handoffs" / "fc-owner.md").write_text("# handoff\n", encoding="utf-8")
        (self.feature_dir / "notes.txt").write_text("local only\n", encoding="utf-8")
        (self.feature_dir / ".issue-tracker.feishu.json").write_text("{}", encoding="utf-8")
        (self.feature_dir / ".issue-tracker.git.json").write_text("{}", encoding="utf-8")
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
            [
                "CONTEXT.md",
                "README.md",
                "handoffs/fc-owner.md",
                "issues/01.md",
                "map.md",
                "maps/wf-map.md",
                "notes.txt",
                "research/facts.md",
                "spec.md",
                "tickets/wf-001.md",
            ],
        )

    def test_ignores_sidecars_when_collecting_sync_files(self) -> None:
        extra_files = self.provider.collect_local_extra_files(self.feature_dir)

        self.assertEqual(extra_files, [])

    def test_maps_canonical_issue_file_to_restore_destination(self) -> None:
        destination = self.provider.restore_destination(
            self.feature_dir,
            "issues/02.md",
        )

        self.assertEqual(destination, self.feature_dir / "issues" / "02.md")

    def test_maps_wayfinder_ticket_file_to_restore_destination(self) -> None:
        destination = self.provider.restore_destination(
            self.feature_dir,
            "tickets/WF-CD-001.md",
        )

        self.assertEqual(destination, self.feature_dir / "tickets" / "WF-CD-001.md")

    def test_rejects_sidecar_restore_destination(self) -> None:
        with self.assertRaises(ValueError):
            self.provider.restore_destination(
                self.feature_dir,
                ".issue-tracker.git.json",
            )
