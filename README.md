# Codex / GPT Daily Journal

把你每天和 Codex、GPT 的真实交互整理成 Markdown 日志，并提交到 GitHub。

这个工具的目标不是“刷绿格子”，而是把真实工作流沉淀成可回看的进展记录：今天问了什么、推进了哪些项目、产出了哪些文件、还有什么后续动作。默认不会上传完整对话原文，只上传摘要型日志，隐私更安全。

## 它会做什么

- 自动读取本机 Codex 会话索引和 session 文件。
- 生成每天一篇日志：`journal/YYYY-MM/YYYY-MM-DD.md`。
- 支持把 ChatGPT 网页/手机端内容放进 `inbox/YYYY-MM-DD.md` 后一起整理。
- 有变更时自动 `git commit`。
- 配好 GitHub 远程仓库后，可自动 `git push`。
- 支持定时运行，做到接近实时同步。

## 目录结构

```text
codex-gpt-journal/
├─ journal/                 # 自动生成的每日记录
├─ inbox/                   # 手动投递 ChatGPT 摘要/导出片段
├─ scripts/
│  ├─ codex_gpt_journal.py  # 主程序
│  ├─ run_once.sh           # 生成并提交一次
│  ├─ watch.sh              # 循环运行，接近实时
│  └─ install_launch_agent.sh
├─ config.example.json
└─ README.md
```

## 快速开始

进入这个目录后，先运行一次：

```bash
python3 scripts/codex_gpt_journal.py --commit
```

如果你已经把这个目录初始化成 Git 仓库，并设置了 GitHub 远程：

```bash
python3 scripts/codex_gpt_journal.py --commit --push
```

## 推荐 GitHub 设置

你可以新建一个私有仓库，例如：

```bash
git init
git branch -M main
git remote add origin git@github.com:你的用户名/codex-gpt-journal.git
```

然后运行：

```bash
python3 scripts/codex_gpt_journal.py --commit --push
```

## 接近实时同步

手动开一个后台窗口：

```bash
./scripts/watch.sh
```

默认每 10 分钟检查一次，有新内容就提交并推送。你也可以改成：

```bash
JOURNAL_INTERVAL_SECONDS=300 ./scripts/watch.sh
```

## macOS 定时运行

先确认 `scripts/install_launch_agent.sh` 里的路径是你想要的路径，然后运行：

```bash
./scripts/install_launch_agent.sh
```

这会创建一个 LaunchAgent，让 macOS 定时执行同步。

## ChatGPT 网页/手机端内容怎么进来？

ChatGPT 网页和手机端没有稳定的本地实时 session 文件，所以这里采用安全、可控的方式：

1. 每天把你想记录的 ChatGPT 内容复制到 `inbox/YYYY-MM-DD.md`。
2. 或者把 ChatGPT 导出的 conversation 摘要整理到当天 inbox 文件。
3. 主程序会把 inbox 内容合并进当天日志。

示例：

```markdown
# ChatGPT notes

- 让 GPT 帮我拆解了论文引言结构。
- 讨论了 GitHub 自动日志的隐私边界。
- 待办：把自动化设成每 10 分钟一次。
```

## 隐私策略

默认模式只记录：

- 会话标题
- 时间
- 用户请求的短摘要
- 助手回复的短摘要
- session 路径
- 手动 inbox 内容

如果你真的想上传完整对话，可以加：

```bash
python3 scripts/codex_gpt_journal.py --include-transcript --commit --push
```

我不建议把公开仓库设成完整对话模式。很多 Codex/GPT 会话里会有客户资料、路径、token、商业想法或未公开研究内容。

