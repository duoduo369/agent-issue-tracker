from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from feishu_issue_tracker.backend import PersistenceBackend, PersistenceBackendError
from feishu_issue_tracker.config import GIT_REPO_PATH_KEY, ResolvedConfig, resolve_config
from feishu_issue_tracker.feishu_backend import FeishuPersistenceBackend
from feishu_issue_tracker.feishu_cli import LarkCliError
from feishu_issue_tracker.git_backend import GitPersistenceBackend
from feishu_issue_tracker.layout import (
    FeatureResolutionError,
    RepoRootNotFoundError,
    ScratchLayoutProvider,
    find_repo_root,
)
from feishu_issue_tracker.pull_service import PullConfirmationRequired, PullService
from feishu_issue_tracker.push_service import PushConfirmationRequired, PushService


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    backend_name: str | None = None

    try:
        repo_root = find_repo_root(Path.cwd())
        resolved_config = resolve_config(repo_root=repo_root)
        backend_name = resolved_config.backend

        if resolved_config.missing_keys:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "backend": resolved_config.backend,
                        "error": "missing_config",
                        "missing_keys": resolved_config.missing_keys,
                        "user_config_path": str(resolved_config.user_config_path),
                        "hint": (
                            "Set the missing keys via environment variables, the repo-root .env file, "
                            "or the user-level config file. See .env.example."
                        ),
                    },
                    indent=2,
                )
            )
            return 2

        backend = resolve_backend(resolved_config=resolved_config)
        layout_provider = ScratchLayoutProvider()

        if args.command == "push":
            service = PushService(layout_provider=layout_provider, backend=backend)
            if args.confirm:
                result = service.execute_push(
                    repo_root=repo_root,
                    cwd=Path.cwd(),
                    feature_name=args.feature,
                    resolved_config=resolved_config,
                    confirm=True,
                )
                payload = {
                    "ok": True,
                    "backend": backend.backend_name,
                    "mode": "execute",
                    "preview": asdict(result.preview),
                    "push_result": result.push_result,
                }
            else:
                preview = service.preview_push(
                    repo_root=repo_root,
                    cwd=Path.cwd(),
                    feature_name=args.feature,
                    resolved_config=resolved_config,
                )
                payload = {
                    "ok": True,
                    "backend": backend.backend_name,
                    "mode": "preview",
                    "preview": asdict(preview),
                }
        else:
            service = PullService(layout_provider=layout_provider, backend=backend)
            if args.confirm:
                result = service.execute_pull(
                    repo_root=repo_root,
                    cwd=Path.cwd(),
                    feature_name=args.feature,
                    resolved_config=resolved_config,
                    confirm=True,
                )
                payload = {
                    "ok": True,
                    "backend": backend.backend_name,
                    "mode": "execute",
                    "preview": asdict(result.preview),
                    "pull_result": result.pull_result,
                }
            else:
                preview = service.preview_pull(
                    repo_root=repo_root,
                    cwd=Path.cwd(),
                    feature_name=args.feature,
                    resolved_config=resolved_config,
                )
                payload = {
                    "ok": True,
                    "backend": backend.backend_name,
                    "mode": "preview",
                    "preview": asdict(preview),
                }
        print(json.dumps(payload, indent=2))
        return 0
    except (FeatureResolutionError, RepoRootNotFoundError, ValueError) as exc:
        payload = {"ok": False, "error": str(exc)}
        if backend_name:
            payload["backend"] = backend_name
        print(json.dumps(payload, indent=2))
        return 1
    except PushConfirmationRequired as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "backend": exc.preview.backend_name,
                    "error": "confirmation_required",
                    "preview": asdict(exc.preview),
                },
                indent=2,
            )
        )
        return 3
    except PullConfirmationRequired as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "backend": exc.preview.backend_name,
                    "error": "confirmation_required",
                    "preview": asdict(exc.preview),
                },
                indent=2,
            )
        )
        return 3
    except (LarkCliError, PersistenceBackendError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "backend": backend_name,
                    "error": getattr(exc, "status", "command_error"),
                    "hint": getattr(exc, "hint", None) or str(exc),
                    "recommended_command": getattr(exc, "recommended_command", None),
                },
                indent=2,
            )
        )
        return 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m feishu_issue_tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("--feature")
    push_parser.add_argument("--confirm", action="store_true")
    pull_parser = subparsers.add_parser("pull")
    pull_parser.add_argument("--feature")
    pull_parser.add_argument("--confirm", action="store_true")
    return parser


def resolve_backend(*, resolved_config: ResolvedConfig) -> PersistenceBackend:
    if resolved_config.backend == "feishu":
        return FeishuPersistenceBackend()
    if resolved_config.backend == "git":
        return GitPersistenceBackend(tracker_repo_path=Path(resolved_config.values[GIT_REPO_PATH_KEY]))
    raise ValueError(f"Unsupported backend {resolved_config.backend!r}.")


if __name__ == "__main__":
    sys.exit(main())
