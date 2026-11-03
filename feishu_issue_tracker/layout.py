from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath


class FeatureResolutionError(ValueError):
    pass


class RepoRootNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalFile:
    rel_path: str
    absolute_path: Path


class ScratchLayoutProvider:
    def resolve_feature_name(
        self,
        *,
        repo_root: Path,
        cwd: Path,
        explicit_feature: str | None,
    ) -> str:
        if explicit_feature and explicit_feature.strip():
            return self.normalize_feature_name(explicit_feature)
        try:
            relative_cwd = cwd.resolve().relative_to(repo_root.resolve())
        except ValueError as exc:
            raise FeatureResolutionError(
                f"{cwd} is not inside repo root {repo_root}"
            ) from exc
        parts = relative_cwd.parts
        if len(parts) >= 2 and parts[0] == ".scratch":
            return self.normalize_feature_name(parts[1])
        raise FeatureResolutionError(
            "Feature could not be inferred from the current directory; pass --feature."
        )

    def feature_dir(self, repo_root: Path, feature_name: str) -> Path:
        return repo_root / ".scratch" / self.normalize_feature_name(feature_name)

    def normalize_feature_name(self, feature_name: str) -> str:
        normalized = feature_name.strip()
        if not normalized:
            raise FeatureResolutionError("Feature name cannot be empty.")
        if normalized in {".", ".."}:
            raise FeatureResolutionError(
                "Feature names must stay within a single .scratch/<feature> directory."
            )
        if normalized.startswith(("/", "\\")) or "/" in normalized or "\\" in normalized:
            raise FeatureResolutionError(
                "Feature names must stay within a single .scratch/<feature> directory."
            )
        if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
            raise FeatureResolutionError(
                "Feature names must stay within a single .scratch/<feature> directory."
            )
        return normalized

    def collect_canonical_files(self, feature_dir: Path) -> list[CanonicalFile]:
        files: list[CanonicalFile] = []
        if not feature_dir.exists():
            return files
        for path in sorted(feature_dir.rglob("*")):
            if not path.is_file():
                continue
            rel_path = path.relative_to(feature_dir).as_posix()
            if self.is_canonical_rel_path(rel_path):
                files.append(
                    CanonicalFile(rel_path=rel_path, absolute_path=path)
                )

        return sorted(files, key=lambda item: item.rel_path)

    def collect_local_extra_files(self, feature_dir: Path) -> list[str]:
        del feature_dir
        return []

    def is_canonical_rel_path(self, rel_path: str) -> bool:
        candidate = PurePosixPath(rel_path)
        windows_candidate = PureWindowsPath(rel_path)
        if (
            not rel_path
            or candidate.is_absolute()
            or windows_candidate.is_absolute()
            or windows_candidate.drive
            or "\\" in rel_path
        ):
            return False
        if any(part in {"", ".", ".."} for part in candidate.parts):
            return False
        return not self.is_sidecar_rel_path(rel_path)

    def is_sidecar_rel_path(self, rel_path: str) -> bool:
        if rel_path == ".feishu-sync.json":
            return True
        return (
            rel_path.startswith(".issue-tracker.")
            and rel_path.endswith(".json")
            and "/" not in rel_path
        )

    def restore_destination(self, feature_dir: Path, rel_path: str) -> Path:
        if not self.is_canonical_rel_path(rel_path):
            raise ValueError(f"{rel_path!r} is not a canonical path.")
        return feature_dir / Path(PurePosixPath(rel_path))


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise RepoRootNotFoundError(f"Could not find repo root from {start}")
