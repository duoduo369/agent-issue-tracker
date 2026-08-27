# agent-issue-tracker

把工作仓库里的 `.scratch/<feature>/` canonical bundle 持久化到一个独立的 issue tracker backend，并在需要时再恢复回来。当前代码已经收口为统一的 Push / Pull 产品面，Feishu 是现有可用 backend，Git backend 的扩展 seam 也已经预留好。

## 最简单的用法

```text
用 /push-to-issue-tracker 推送 multi-backend-issue-tracker
用 /pull-from-issue-tracker 拉回 multi-backend-issue-tracker
```

用户不需要按 backend 记不同命令。当前生效 backend 由配置决定。

## 配置

优先在仓库根目录放 `.env`，可以直接参考 `.env.example`：

```text
AGENT_ISSUE_TRACKER_BACKEND=feishu
AGENT_ISSUE_TRACKER_REPO_NAME=
AGENT_ISSUE_TRACKER_FEISHU_ROOT_FOLDER_TOKEN=
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

- `Reference/`: skill 运行时要遵循的流程材料
- `Docs/`: 面向开发者的架构说明和 backend 扩展契约
- `DOMAIN_CONTEXT.md`: 共享语言和术语边界
