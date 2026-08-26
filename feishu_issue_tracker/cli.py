from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from feishu_issue_tracker.config import UserConfigStore, default_user_config_path, resolve_config
from feishu_issue_tracker.feishu_cli import LarkCliError, LarkCliFeishuClient
from feishu_issue_tracker.layout import FeatureResolutionError, RepoRootNotFoundError, ScratchLayoutProvider, find_repo_root
from feishu_issue_tracker.push_service import PushConfirmationRequired, PushService


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "config" and args.config_command == "write":
        store = UserConfigStore(args.path) if args.path else UserConfigStore(default_user_config_path())
        values = {"FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN": args.root_folder_token}
        if args.repo_name:
            values["FEISHU_ISSUE_TRACKER_REPO_NAME"] = args.repo_name
        store.save(values)
        print(json.dumps({"ok": True, "path": str(store.path)}, indent=2))
        return 0

    if args.command != "push":
        parser.error("Unknown command")

    try:
        repo_root = find_repo_root(Path.cwd())
        resolved_config = resolve_config(repo_root=repo_root)
        if resolved_config.missing_keys:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "missing_config",
                        "missing_keys": resolved_config.missing_keys,
                        "user_config_path": str(resolved_config.user_config_path),
                    },
                    indent=2,
                )
            )
            return 2

        service = PushService(
            layout_provider=ScratchLayoutProvider(),
            feishu_client=LarkCliFeishuClient(),
        )
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
                "mode": "preview",
                "preview": asdict(preview),
            }
        print(json.dumps(payload, indent=2))
        return 0
    except (FeatureResolutionError, RepoRootNotFoundError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    except PushConfirmationRequired as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "confirmation_required",
                    "preview": asdict(exc.preview),
                },
                indent=2,
            )
        )
        return 3
    except LarkCliError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m feishu_issue_tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("--feature")
    push_parser.add_argument("--confirm", action="store_true")

    config_parser = subparsers.add_parser("config")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_write_parser = config_subparsers.add_parser("write")
    config_write_parser.add_argument("--root-folder-token", required=True)
    config_write_parser.add_argument("--repo-name")
    config_write_parser.add_argument("--path", type=Path)
    return parser


if __name__ == "__main__":
    sys.exit(main())
