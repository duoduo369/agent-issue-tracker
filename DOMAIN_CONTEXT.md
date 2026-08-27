# Agent Issue Tracker Domain Context

这个文档定义 agent issue tracker 项目的共享语言。它的作用是让产品、skill 和 backend 相关讨论在项目从单一持久化方案扩展到多 backend 时，仍然保持一致。

## Language

**Issue Tracker**:
用于在工作仓库之外保存和恢复项目 issue 跟踪产物的持久化系统。
_Avoid_: 云盘, 同步目标, 存储

**Backend**:
Issue Tracker 选用的持久化机制，例如 Feishu 或 Git。
_Avoid_: provider, transport, plugin

**Source Repo**:
当前正在工作的仓库，也就是包含本地 `.scratch/<feature>` 并发起 push 或 pull 的仓库。
_Avoid_: tracker repo, remote repo

**Tracker Workspace**:
由 backend 持有的工作位置，持久化后的 issue tracker 内容会在这里被暂存、更新或读回。
_Avoid_: source repo, 本地镜像仓库

**Canonical Bundle**:
某个 feature 下被视为权威持久化内容的那组 issue tracker 文件。
_Avoid_: scratch 目录, 整个 feature 目录, 备份

**Feature**:
`.scratch/<feature>` 下的一个命名单元，它的 canonical bundle 会作为一个整体被持久化。
_Avoid_: branch, ticket 集合, project

**Push**:
把 source repo 中的 canonical bundle 推成当前 backend 里最新持久化状态的操作。
_Avoid_: 备份, 上传

**Pull**:
把当前 backend 中的 canonical bundle 恢复回 source repo，并以 backend 副本为最新持久化状态的操作。
_Avoid_: 下载, 合并

**Reference**:
skill 在执行时会读取的 agent-facing 材料，用来遵循项目流程或 backend 分支流程。
_Avoid_: docs, manual

**Docs**:
面向开发者的架构材料，用来说明项目的设计边界和扩展模型。
_Avoid_: reference, 运行时说明
