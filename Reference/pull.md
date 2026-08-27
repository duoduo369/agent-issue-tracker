# Pull Reference

`pull` 的公共流程负责把当前 backend 中某个 feature 的 canonical bundle 恢复回 source repo。

## Runtime Checklist

1. 解析 feature。
2. 定位 backend 中对应的 repo / feature 目标。
3. 生成 preview，并分类展示：
   `will_create` / `will_overwrite` / `local_only_canonical` / `remote_extra_files` / `local_extra_files`
4. 有风险时等待明确确认。
5. 执行 pull，并只恢复 canonical 文件。
6. 更新当前 backend 的 sidecar。

## Notes

- `pull` 的语义是“以 backend 中的持久化副本为最新状态”。
- extra 文件不会被自动写回 source repo。
- 如果 repo 或 feature 目标不存在，应明确告诉用户当前没有可恢复的 canonical bundle。
