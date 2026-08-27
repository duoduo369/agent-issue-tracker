from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from feishu_issue_tracker.config import resolve_config
from feishu_issue_tracker.feishu_cli import LarkCliDoctorResult, LarkCliError, LarkCliFeishuClient
from feishu_issue_tracker.layout import FeatureResolutionError, RepoRootNotFoundError, ScratchLayoutProvider, find_repo_root
from feishu_issue_tracker.push_service import PushConfirmationRequired, PushService


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root(Path.cwd())
        resolved_config = resolve_config(repo_root=repo_root)
        client = LarkCliFeishuClient()
        lark_cli = client.doctor()

        if args.command == "doctor":
            payload = {
                "ok": not resolved_config.missing_keys and lark_cli.ready,
                "mode": "doctor",
                "repo_root": str(repo_root),
                "access_strategy": {
                    "preferred": client.preferred_access_strategy(),
                    "fallback": "user_fallback",
                    "user_fallback_scopes": client.user_fallback_scopes(),
                },
                "config": {
                    "values": resolved_config.values,
                    "sources": resolved_config.sources,
                    "missing_keys": resolved_config.missing_keys,
                },
                "lark_cli": asdict(lark_cli),
            }
            print(json.dumps(payload, indent=2))
            return 0 if payload["ok"] else 1

        if resolved_config.missing_keys:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "missing_config",
                        "missing_keys": resolved_config.missing_keys,
                        "hint": "Set the missing keys via environment variables or add them to the repo-root .env file. See .env.example.",
                    },
                    indent=2,
                )
            )
            return 2

        if not lark_cli.ready:
            print(json.dumps(_lark_cli_error_payload(lark_cli), indent=2))
            return 4

        service = PushService(layout_provider=ScratchLayoutProvider(), feishu_client=client)
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
        print(
            json.dumps(
                {
                    "ok": False,
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

    subparsers.add_parser("doctor")
    push_parser = subparsers.add_parser("push")
    push_parser.add_argument("--feature")
    push_parser.add_argument("--confirm", action="store_true")
    return parser


def _lark_cli_error_payload(result: LarkCliDoctorResult) -> dict:
    return {
        "ok": False,
        "error": result.status,
        "hint": result.hint,
        "recommended_command": result.recommended_command,
    }


if __name__ == "__main__":
    sys.exit(main())
