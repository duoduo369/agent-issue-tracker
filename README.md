# agent-issue-tracker

把 matt skill 本地的issue文件 （.scratch/<feature>/`）持久化到一个独立的 issue tracker backend，例如飞书或者git，并且支持需要时再恢复回来以应对某些团队合作。

## 最简单的用法

```text
用 /push-to-issue-tracker 推送 multi-backend-issue-tracker
用 /pull-from-issue-tracker 拉回 multi-backend-issue-tracker
```

用户不需要按 backend 记不同命令。当前生效 backend 由配置决定；如果没有显式配置，默认使用 git backend。

## 配置

优先在仓库根目录放 `.env`，可以直接参考 `.env.example`：

```text
AGENT_ISSUE_TRACKER_BACKEND=git
AGENT_ISSUE_TRACKER_REPO_NAME=
AGENT_ISSUE_TRACKER_GIT_REPO_PATH=
```

支持的配置来源优先级：

1. 环境变量
2. 仓库根目录 `.env`
3. 用户级配置文件

## Canonical Bundle

只会处理这些文件：

- `spec.md`
- `map.md`
- `issues/*.md`

其他文件会在 preview 里作为 extra 提醒，但不会被默认同步。

## 文档分层

- `reference/`: skill 运行时要遵循的流程材料
- `docs/`: 面向开发者的架构说明和 backend 扩展契约
- `DOMAIN_CONTEXT.md`: 共享语言和术语边界
