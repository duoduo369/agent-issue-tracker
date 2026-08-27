# 02 — 实现 Git Backend 的 Push / Pull 持久化能力

**What to build:** 当 Git 是当前 Backend 时，让工具按统一的 preview / confirm / execute 流程完成完整持久化。Push 会把 Source Repo 的 Canonical Bundle 复制到 Tracker Workspace 的目标位置后自动 commit 并 push，失败时默认 rebase 后重试；Pull 会先更新 Tracker Workspace，再把远端 Canonical Bundle 覆盖恢复回 Source Repo，并清楚提示覆盖方向。

**Blocked by:** None — 01 已完成，可开始实现。

**Status:** ready-for-agent

- [ ] Git Backend 可以在 `<source-repo>/<feature>/...` 目标布局下完成 Push，并保持与通用流程一致的 preview、确认和 extras 提示语义。
- [ ] Git Backend 可以先更新 Tracker Workspace 再完成 Pull 恢复，并在 Pull 中以远端内容为准覆盖 Canonical Bundle。
- [ ] Git Backend 的自动 commit、push、rebase 重试和 sidecar 隔离行为都有对应验证，且不会破坏 Feishu Backend 的既有行为。
