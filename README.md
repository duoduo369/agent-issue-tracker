# feishu-issue-tracker

把matt skill本地的.scratch按feature推送到飞书云盘，做持久化。事实上，如果你单纯只为了落盘做持久化的话，另外专门用一个issue-tracker的git项目也可以做相同的事情，并且git的项目还有git的管理。
不直接用github、gitlab的issue功能是因为团队合作中如果直接用对应项目的issue功能，可以说项目的issue管理就乱七八糟。

todo: 未来可能也会支持superpowers的格式。

## 安装

使用的harness，无论是codex、dsh还是其他harness，输入这个项目地址，让他安装这个skill。


## 最简单的用法
```text
用 /push-issue-to-feishu-tracker 推送 feishu-local-first-sync。
用 /pull-issue-from-feishu-tracker 拉回 feishu-local-first-sync。
```

## 你通常只需要提供什么

- 飞书目标文件夹链接
- 如果 agent 没法自己判断要推哪一份内容，再补一句 feature 名

如果 agent 提到 `folder token`，你不用自己拆，直接把整个飞书文件夹链接贴给它就行。
如果 agent 让你确认拉取，同样直接明确回复“拉取”或“确认拉取”。


## 第一次使用时，你可能会被要求做什么

这是正常的。按提示完成即可：

- 在飞书开放平台，某个应用发布一个新版本
- 打开 agent 发来的授权链接
- 扫二维码或点击确认授权

如果 agent 让你提供链接，就贴飞书文件夹链接。  
如果 agent 让你“确认推送”，直接明确回复“推送”或“确认推送”。
