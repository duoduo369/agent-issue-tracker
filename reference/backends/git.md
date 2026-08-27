# Git Backend Reference

当当前 backend 是 `git` 时，runtime 分支遵循这些补充规则：

- 默认 backend 就是 `git`；如果需要显式指定，也应把 `AGENT_ISSUE_TRACKER_BACKEND` 设为 `git`。
- `AGENT_ISSUE_TRACKER_GIT_REPO_PATH` 必须指向一个已存在、已配置 remote 的 tracker workspace。
- 如果设置了 `AGENT_ISSUE_TRACKER_GIT_BRANCH`，运行时应先切到该分支；如果没设置，就沿用 tracker workspace 当前分支。
- `pull` 的 preview 必须先刷新 tracker workspace，再让用户确认；不要让用户对过期状态做确认。
- `push` 在远端先行变化时，会先用 rebase 更新 tracker workspace，再重试 push。
- `pull` 的覆盖方向以 tracker workspace 中最新持久化内容为准，只会恢复 canonical 文件。
