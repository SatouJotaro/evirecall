# 团队 Git 与 PR 协作指南

观察日期：2026-10-31。`main` 当前未启用分支保护；离线 CI 仅有 `ci/offline-checks.yml` 模板，尚未作为 `.github/workflows/` 工作流启用。以下评审流程是团队操作约定，不代表 GitHub 已强制执行。合并前仍需运行本地检查。

## 每次开始：先确认自己在哪里

在仓库根目录运行：

```powershell
git status --short
git branch --show-current
git fetch origin
git branch -a
```

`fetch` 只更新远端引用，不会把同伴的文件合进当前分支。若 `status` 有改动，先确认属于哪个任务，提交到该任务分支或妥善保存，再切换。不要盲目使用 `reset --hard`、清理文件或 force push 来“同步”。遇到冲突先读差异，与相关负责人一起处理。

## 从更新后的 main 开一个任务分支

确认本地改动已处理后：

```powershell
git switch main
git pull --ff-only origin main
git switch -c xiaochen/smurfs-adapter
```

示例分支名可替换为 `bijun/stale-adapter` 或 `tangchengyu/evaluation-harness`；每个新任务使用独立分支。`pull --ff-only` 若失败，先查看本地和远端差异，不通过强制覆盖解决。

编辑后先检查 diff，运行 README 的本地检查，再只提交自己的文件：

```powershell
git diff --check
git diff
git add path/to/your-file
git commit -m "Add Smurfs adapter"
git push -u origin xiaochen/smurfs-adapter
```

`path/to/your-file` 是占位路径，需替换为实际文件；多个文件逐项确认后添加。密钥、`.env`、大型数据、vendor 和运行产物遵循现有忽略规则，不要强制加入。提交说明描述实际改动，保留合法作者及许可证信息。

## PR、评审、合并

在 GitHub 创建面向 `main` 的 PR；未准备好验收时使用 Draft。写清解决什么问题、改动边界、复现命令、检查结果与限制，按[交接登记](team-handoff.md)填写对应 ID。请指定评审人；公共接口或共享语义变更请另外两位评审。收到修改意见后继续提交到同一分支，PR 会更新。

评审通过、问题解决且本地检查完成后再合并。不要直接将工作分支推到 `main`，也不要因当前没有分支保护而跳过评审。负责人交付 PR，Chengyu 在 PR 中确认接入与目标 commit；登记表的“已验收”和“已集成”分别记录。

## 同伴的 PR 尚未合并：必须切到它的分支才能试用

只在 `main` 上执行 `pull` 不会收到尚未合并的 PR 内容。先处理自己的未提交改动，`fetch` 后确认真实远端分支，再创建本地跟踪分支：

```powershell
git fetch origin
git branch -r
git switch --track origin/tangchengyu/evaluation-harness
```

若本地已有同名分支，使用 `git switch tangchengyu/evaluation-harness`，确认工作区干净后再 `git pull --ff-only`。若需另取本地名字，可用 `git switch -c review/evaluation-harness --track origin/tangchengyu/evaluation-harness`。命令中的远端分支必须已存在；PR 页面确认其最新 commit，再按 README 安装与验证。评审时避免顺手加入无关改动。

## 合并之后与下一个任务

确认自己的任务已合并，处理完本地改动，再回到更新后的 `main`，从那里开下一条分支：

```powershell
git switch main
git pull --ff-only origin main
git switch -c xiaochen/next-task
```

不要继续把下一项工作叠到已经合并的旧分支。若新任务必须提前依赖未合并 PR，在新 PR 说明依赖分支/commit，协调合并顺序。不要擅自重写同伴的分支历史。
