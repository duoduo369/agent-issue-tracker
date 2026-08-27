---
name: pull-issue-from-feishu-tracker
description: "Preview and pull one `.scratch/<feature>` issue bundle from Feishu Drive."
disable-model-invocation: true
---

在用户明确要求把飞书云盘中的 `.scratch/<feature>` canonical 产物恢复到本地时使用。

## Steps

1. 解析 feature。

- 如果用户已经指定了 feature，透传给 `--feature`。
- 如果用户没有指定，就依赖当前目录自动识别。
- 如果工具返回无法识别 feature，再向用户确认 feature 名。

2. 先做体检，确认本地依赖状态。

- 在目标仓库中运行 `python -m feishu_issue_tracker doctor`。
- 如果 `config.missing_keys` 非空，向用户索取：
  - `FEISHU_ISSUE_TRACKER_ROOT_FOLDER_TOKEN`：必填
  - `FEISHU_ISSUE_TRACKER_REPO_NAME`：可选
- 让用户把这些值写进环境变量或仓库根目录 `.env`；优先推荐直接参考 `.env.example` 在仓库根目录创建 `.env`。
- 如果返回 `lark_cli.status != "ready"`，优先按照 `recommended_command` 引导用户完成初始化或登录，再重新执行体检。
- 优先按 `bot-first` 理解结果：如果 bot 能访问目标文件夹，不要额外要求用户授权。
- 只有当工具明确返回 `user_identity_missing` 或 `missing_scope` 时，才进入 `user-fallback`。
- 一旦进入 `user-fallback`，优先引导用户一次性完成完整 user scope 集合，而不是边跑边补：
  - `space:document:retrieve`
  - `space:folder:create`
  - `drive:drive.metadata:readonly`
  - `drive:file:upload`
  - `drive:file:download`
- 如果开发者后台刚新增了这些用户权限，先让用户发布一个新版本，再做这一轮合并授权。

3. 先做预演，不要直接写本地。

- 在目标仓库中运行 `python -m feishu_issue_tracker pull`；必要时补 `--feature <name>`。

4. 清楚地总结预演结果。

- 说明解析出的 repo 名和 feature 名。
- 只在非空时汇报这些桶：
  - `will_create`
  - `will_overwrite`
  - `local_only_canonical`
  - `remote_extra_files`
  - `local_extra_files`
- 明确提醒：只会恢复 canonical 文件，也就是 `spec.md`、`map.md` 和 `issues/*.md`。
- 如果工具提示远端 repo 或 feature 目录不存在，直接告诉用户当前没有可拉取的 canonical 目录，不要继续执行。

5. 等用户确认。

- 在真正写本地前，必须拿到明确的同意。
- 如果存在覆盖风险、仅本地 canonical 文件或额外文件，要在确认问题里点明哪些内容会恢复，哪些不会自动同步。

6. 执行 pull。

- 运行 `python -m feishu_issue_tracker pull --confirm`；必要时补 `--feature <name>`。
- 如果工具提示 `lark-cli` 未安装、未配置或未登录，停止执行并把问题告诉用户，不要绕过这条路径去直接写飞书。

## Done When

- 用户已经看过预演结果。
- 用户确认后，pull 已执行成功。
- 你已经告知本地 `.scratch/<feature>/` canonical 文件已恢复，并说明本地 `.feishu-sync.json` sidecar 已更新。
