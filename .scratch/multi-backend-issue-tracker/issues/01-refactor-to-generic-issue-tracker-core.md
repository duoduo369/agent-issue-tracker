# 01 — 重构为通用 Issue Tracker 核心并保持 Feishu Backend 可用

**What to build:** 把当前项目从单一 Feishu 持久化工具重构为通用 Issue Tracker 架构。用户面只保留两个通用命令，项目结构重组为适合多 Backend 的形态，`Reference` 与 `Docs` 职责清晰分层，公共 Push/Pull 流程与 Backend adapter contract 被抽出，并且 Feishu 继续能通过新架构完成完整的 preview、确认和执行流程。

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] 用户面只保留两个通用命令，且不再按 Backend 暴露不同 skill 命令。
- [x] 公共 Push/Pull 流程、Backend adapter contract、`AGENT_...` 配置模型和 Backend-specific sidecar 已落成，Feishu 在新架构下仍然可用。
- [x] `Reference` 与 `Docs` 已按约定分层，且 `Docs` 中有面向开发者的 Backend 扩展架构说明。
