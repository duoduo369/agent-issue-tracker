---
name: push-issue-to-feishu-tracker
description: "Preview and push one `.scratch/<feature>` issue bundle to Feishu Drive."
disable-model-invocation: true
---

Use this when the user explicitly wants to push a Matt-style local issue bundle from `.scratch/<feature>/` into Feishu Drive.

## Steps

1. Resolve the target feature.

- If the user already named a feature, pass it through with `--feature`.
- Otherwise rely on auto-detection from the current directory. If the tool says the feature cannot be inferred, ask the user for the feature name before continuing.

2. Preview before any write.

- Run `python -m feishu_issue_tracker push` from the target repo, adding `--feature <name>` when needed.
- If the command reports `missing_config`, ask the user for:
  - `FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN` (required)
  - `FEISHU_ISSUE_TRACKER_REPO_NAME` (optional override)
- Save the provided values with `python -m feishu_issue_tracker config write --root-folder-token <token>`, adding `--repo-name <name>` only when the user supplied it.
- Re-run the preview after saving config.

3. Summarize the preview clearly.

- Report the resolved repo name and feature name.
- Call out these buckets when they are non-empty:
  - `will_create`
  - `will_overwrite`
  - `remote_only_canonical`
  - `remote_extra_files`
  - `local_extra_files`
- Make it clear that only canonical files are pushed: `spec.md`, `map.md`, and `issues/*.md`.

4. Ask for confirmation.

- Always wait for a clear yes before the write step.
- If the preview shows overwrite risk or extra files, mention that explicitly in the confirmation question.

5. Execute the push.

- Run `python -m feishu_issue_tracker push --confirm`, again passing `--feature <name>` when needed.
- If the command surfaces a `lark-cli` install/config/login problem, stop and show the message instead of improvising a different remote write path.

## Done When

- The user has seen the preview.
- The confirmed push has been executed successfully.
- You report the resolved remote repo/feature path and note that the local `.feishu-sync.json` sidecar has been updated.
