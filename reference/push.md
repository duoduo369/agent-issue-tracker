# Push Reference

`push` 的公共流程只做一件事：把 source repo 中某个 feature 的 canonical bundle 推成当前 backend 里的最新状态。

## Runtime Checklist

1. 解析 feature。
2. 识别 canonical bundle。
3. 生成 preview，并分类展示：
   `will_create` / `will_overwrite` / `remote_only_canonical` / `remote_extra_files` / `local_extra_files`
4. 汇报 preview 后直接继续执行，不因风险提示停下来等待确认。
5. 调用当前 backend 完成 push。
6. 更新当前 backend 的 sidecar。

## Notes

- 公共层只处理 canonical bundle，不处理 extra 文件同步。
- preview 里的 locator 字段是 backend-agnostic 的；不要在公共层把它重新解释成 provider-specific 术语。
- 切换 backend 是配置行为，不是 feature 状态迁移。
