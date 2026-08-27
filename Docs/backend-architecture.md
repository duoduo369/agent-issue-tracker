# Backend Architecture

这个项目现在按“公共 issue tracker 流程 + backend adapter”来分层。

## Common Layer

公共层负责这些稳定职责：

- 从 source repo 解析 feature
- 识别 canonical bundle
- 为 preview 分类 create / overwrite / extras
- 决定是否需要确认
- 为 push / pull 做本地 staging 和恢复
- 读写 backend-specific sidecar

这些职责不应该知道具体 provider 的鉴权细节，也不应该重新发明 provider-specific 的路径模型。

## Backend Contract

一个 backend adapter 需要实现这些能力：

- 从配置中解析自己的根 locator
- 定位 repo 和 feature 目标
- 在需要时创建 repo 或 feature 目标
- 报告统一的 `SyncStatus`
- 执行 push / pull
- 在真正写入前完成自己的 readiness 检查

公共层只依赖统一的 locator 概念，而不依赖 “folder token”“git path” 之类的 provider 术语。

## Two-Layer I/O Model

这个项目的核心是两层 I/O：

1. `source repo <-> canonical staging`
   这是公共 issue tracker 逻辑，决定什么算 canonical、怎样 preview、怎样恢复。
2. `canonical staging <-> tracker workspace`
   这是 backend 逻辑，决定怎样定位、比较和持久化 backend 中的目标。

如果未来新增 backend，优先判断逻辑属于哪一层，再决定放在公共层还是 adapter 内。

## Sidecars

- sidecar 按 backend 隔离，命名为 `.issue-tracker.<backend>.json`
- sidecar 只缓存某个 backend 的 locator / binding 信息
- sidecar 不决定当前 active backend；active backend 只来自配置

## Feishu Today, Git Next

Feishu 现在通过这个 contract 运行。Git backend 的实现可以在不复制公共 preview / restore 逻辑的前提下接入同一套服务层，这就是本次重构的主要目标。
