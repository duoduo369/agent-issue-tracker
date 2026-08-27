# Feishu Backend Reference

当当前 backend 是 `feishu` 时，runtime 分支遵循这些补充规则：

- 先按 bot-first 理解结果；如果 bot 可以访问目标文件夹，不要额外要求用户授权。
- 只有当工具明确返回 `user_identity_missing` 或 `missing_scope` 时，才进入 user-fallback。
- 一旦进入 user-fallback，优先一次性完成完整 scope 集合：
  - `space:document:retrieve`
  - `space:folder:create`
  - `drive:drive.metadata:readonly`
  - `drive:file:upload`
  - `drive:file:download`
- 若返回 `recommended_command`，优先按该命令引导用户完成初始化或授权。
- Feishu sidecar 现在使用 `.issue-tracker.feishu.json`；旧的 `.feishu-sync.json` 会继续被兼容读取。
