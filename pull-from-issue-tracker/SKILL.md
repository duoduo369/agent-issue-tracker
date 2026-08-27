---
name: pull-from-issue-tracker
description: "Preview and pull one `.scratch/<feature>` canonical bundle from the configured issue tracker backend."
disable-model-invocation: true
---

在用户明确要求把 issue tracker 中的 `.scratch/<feature>` canonical bundle 恢复到本地时使用。

先阅读：

- `Reference/pull.md`
- `Reference/backends/feishu.md`（当当前 backend 是 `feishu` 时）
- `Reference/backends/git.md`（当当前 backend 是 `git` 时）

## Steps

1. 解析 feature。

- 如果用户已经指定了 feature，透传给 `--feature`。
- 如果用户没有指定，就依赖当前目录自动识别。
- 如果工具返回无法识别 feature，再向用户确认 feature 名。

2. 先做预演。

- 在目标仓库中运行 `python -m feishu_issue_tracker pull`；必要时补 `--feature <name>`。
- 如果返回 `missing_config`，按 `missing_keys` 引导用户补齐配置；优先建议参考仓库根目录 `.env.example` 创建 `.env`。
- 如果返回 `recommended_command`，优先按推荐命令完成初始化或登录，再重新执行预演。
- 如果工具提示远端 repo 或 feature 不存在，直接告诉用户当前没有可拉取的 canonical bundle，不要继续执行。

3. 清楚总结 preview。

- 说明当前 backend、repo 名和 feature 名。
- 只在非空时汇报这些桶：
  - `will_create`
  - `will_overwrite`
  - `local_only_canonical`
  - `remote_extra_files`
  - `local_extra_files`
- 明确提醒：只会恢复 canonical 文件，也就是 `spec.md`、`map.md` 和 `issues/*.md`。

4. 等用户确认。

- 在真正写本地前，必须拿到明确的同意。
- 如果存在覆盖风险、仅本地 canonical 文件或额外文件，要点明哪些内容会恢复，哪些不会自动同步。

5. 执行 pull。

- 运行 `python -m feishu_issue_tracker pull --confirm`；必要时补 `--feature <name>`。

## Done When

- 用户已经看过预演结果。
- 用户确认后，pull 已执行成功。
- 你已经告知本地 `.scratch/<feature>/` canonical 文件已恢复，并说明对应 backend sidecar 已更新。
