---
name: push-to-issue-tracker
description: "Preview and push one `.scratch/<feature>` canonical bundle to the configured issue tracker backend."
disable-model-invocation: true
---

在用户明确要求把本地 `.scratch/<feature>/` canonical bundle 推送到 issue tracker 时使用。

先阅读：

- `reference/push.md`
- `reference/backends/feishu.md`（当当前 backend 是 `feishu` 时）
- `reference/backends/git.md`（当当前 backend 是 `git` 时）

## Steps

1. 解析 feature。

- 如果用户已经指定了 feature，透传给 `--feature`。
- 如果用户没有指定，就依赖当前目录自动识别。
- 如果工具返回无法识别 feature，再向用户确认 feature 名。

2. 先做预演。

- 在目标仓库中运行 `python -m feishu_issue_tracker push`；必要时补 `--feature <name>`。
- 如果返回 `missing_config`，按 `missing_keys` 引导用户补齐配置；优先建议参考仓库根目录 `.env.example` 创建 `.env`。
- 如果返回 `recommended_command`，优先按推荐命令完成初始化或登录，再重新执行预演。

3. 清楚总结 preview。

- 说明当前 backend、repo 名和 feature 名。
- 只在非空时汇报这些桶：
  - `will_create`
  - `will_overwrite`
  - `remote_only_canonical`
  - `remote_extra_files`
  - `local_extra_files`
- 明确提醒：只会推送 canonical 文件，也就是 `spec.md`、`map.md` 和 `issues/*.md`。

4. 直接执行 push。

- 预演完成后，默认继续执行，不要因为 overwrite、remote_only_canonical、remote_extra_files 或 local_extra_files 停下来向用户确认。
- 运行 `python -m feishu_issue_tracker push --confirm`；必要时补 `--feature <name>`。

## Done When

- 用户已经看过预演结果。
- push 已执行成功。
- 你已经告知 backend 目标位置，并说明对应 backend sidecar 已更新。
