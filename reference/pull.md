# Pull Reference

`pull` 的公共流程负责把当前 backend 中某个 feature 的 bundle 恢复回 source repo。

## Runtime Checklist

1. 解析 feature。
2. 定位 backend 中对应的 repo / feature 目标。
3. 生成 preview，并分类展示：
   `will_create` / `will_overwrite` / `local_only_canonical` / `remote_extra_files` / `local_extra_files`
4. 汇报 preview 后直接继续执行，不因风险提示停下来等待确认。
5. 执行 pull，并恢复 `.scratch/<feature>/` 下除 sidecar 外的全部文件。
6. 更新当前 backend 的 sidecar。

## Notes

- `pull` 的语义是“以 backend 中的持久化副本为最新状态”。
- sidecar 例如 `.issue-tracker.<backend>.json` 和 `.feishu-sync.json` 不会被远端副本覆盖。
- 如果 repo 或 feature 目标不存在，应明确告诉用户当前没有可恢复的 feature bundle。
