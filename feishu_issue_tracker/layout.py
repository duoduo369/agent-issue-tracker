from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class FeatureResolutionError(ValueError):
    pass


class RepoRootNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalFile:
    rel_path: str
    absolute_path: Path


class ScratchLayoutProvider:
    sidecar_name = ".feishu-sync.json"

    def resolve_feature_name(
        self,
        *,
        repo_root: Path,
        cwd: Path,
        explicit_feature: str | None,
    ) -> str:
        if explicit_feature and explicit_feature.strip():
            return explicit_feature.strip()
        try:
            relative_cwd = cwd.resolve().relative_to(repo_root.resolve())
        except ValueError as exc:
            raise FeatureResolutionError(
                f"{cwd} is not inside repo root {repo_root}"
            ) from exc
        parts = relative_cwd.parts
        if len(parts) >= 2 and parts[0] == ".scratch":
            return parts[1]
        raise FeatureResolutionError(
            "Feature could not be inferred from the current directory; pass --feature."
        )

    def feature_dir(self, repo_root: Path, feature_name: str) -> Path:
        return repo_root / ".scratch" / feature_name

    def collect_canonical_files(self, feature_dir: Path) -> list[CanonicalFile]:
        files: list[CanonicalFile] = []
        for filename in ("spec.md", "map.md"):
            candidate = feature_dir / filename
            if candidate.is_file():
                files.append(CanonicalFile(rel_path=filename, absolute_path=candidate))

        issues_dir = feature_dir / "issues"
        if issues_dir.is_dir():
            for issue_file in sorted(issues_dir.glob("*.md")):
                files.append(
                    CanonicalFile(
                        rel_path=issue_file.relative_to(feature_dir).as_posix(),
                        absolute_path=issue_file,
                    )
                )

        return sorted(files, key=lambda item: item.rel_path)

    def collect_local_extra_files(self, feature_dir: Path) -> list[str]:
        extras: list[str] = []
        for path in sorted(feature_dir.rglob("*")):
            if not path.is_file():
                continue
            rel_path = path.relative_to(feature_dir).as_posix()
            if rel_path == self.sidecar_name:
                continue
            if self.is_canonical_rel_path(rel_path):
                continue
            extras.append(rel_path)
        return extras

    def is_canonical_rel_path(self, rel_path: str) -> bool:
        if rel_path in {"spec.md", "map.md"}:
            return True
        return rel_path.startswith("issues/") and rel_path.count("/") == 1 and rel_path.endswith(".md")


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise RepoRootNotFoundError(f"Could not find repo root from {start}")
