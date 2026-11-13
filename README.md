# releases-watcher

![releases-watcher](./assets/logo.png)

**releases-watcher** 是一个基于 **GitHub Actions** 的 Releases 自动监控工具。  
它可以持续监控指定的 **GitHub** 或 **Codeberg** 仓库，并在发布新版本时通过 **Telegram Bot** 发送通知。

无需服务器、无需数据库、无需长期运行脚本。

所有逻辑都运行在 GitHub Actions 中。

---

## 功能特点

- 支持监控多个 GitHub 仓库
- 支持监控 Codeberg（codeberg.org，Forgejo）仓库
- 优先用 RSS/Atom 源探测变化，只有真的变了才调 API，省配额
- 新版本发布自动 Telegram 推送
- 新加入监控的仓库自动发送首次通知
- 自动避免重复推送
- 支持手动检查并发送结果摘要
- 无需服务器，完全基于 GitHub Actions
- 配置简单，依赖极少

---

## 工作原理

每次运行时，程序会执行以下流程：

1. 从 `repos.json` 读取需要监控的仓库列表
2. 读取仓库的 `releases.atom` 源（GitHub / Codeberg 都提供），取最新一条的 tag
3. 与本地记录的版本比较；没变化就直接跳过，**不消耗任何 API 配额**
4. 有变化时才调用 API（`api.github.com` / `codeberg.org/api/v1`）确认最新正式 Release
5. 如果 API 确认是新版本，则发送 Telegram 通知
6. 将最新版本写入状态文件，避免重复通知

> RSS 只负责“发现有没有新东西”，最终以 API 结果为准。因为 feed 里没有 `draft` / `prerelease` 标记，
> 直接拿 feed 第一条会导致 nightly / beta / RC 疯狂推送；现在的做法是 feed 报变化后用 API 过滤，
> 日志里会打印 `Prerelease only, skip: ...`。

状态文件保存在仓库内：

`.releases-watcher/ └── telegram/ └── owner__repo.txt`

每个文件记录一个仓库已经通知过的最新版本号。

例如：

`.releases-watcher/telegram/microsoft__vscode.txt`

文件内容：

`1.89.0`

Codeberg 仓库的状态文件名会带上平台前缀，避免与同名 GitHub 仓库冲突：

`.releases-watcher/telegram/codeberg__forgejo__forgejo.txt`

---

## 示例通知

Telegram 消息示例：

```
GitHub Release Update

Repo: cli/cli Name: GitHub CLI 2.74.2 Tag: v2.74.2 Previous: v2.74.1

Open Release
```

---

## 快速开始

### 1 创建仓库

创建一个 GitHub 仓库，并添加以下文件：

`.github/workflows/releases-watcher-telegram.yml releases-watcher/telegram_watcher.py releases-watcher/repos.json`

---

### 2 创建 Telegram Bot

在 Telegram 中使用 **BotFather** 创建机器人。

获取：

```
- Bot Token
- Chat ID
```

---

### 3 添加 GitHub Secrets

进入仓库：

`Settings → Secrets → Actions`

添加两个 Secret：

`TG_BOT_TOKEN TG_CHAT_ID`

---

### 4 配置需要监控的仓库

编辑文件：

releases-watcher/repos.json

默认按 GitHub 仓库处理，直接写 `owner/repo`：

```json
[
  "microsoft/vscode",
  "cli/cli",
  "hashicorp/terraform"
]
```

监控 Codeberg 仓库时，在条目前加上 `codeberg:` 前缀（也接受 `codeberg.org/owner/repo` 这种写法）：

```json
[
  "microsoft/vscode",
  "codeberg:forgejo/forgejo",
  "codeberg.org/forgejo/runner"
]
```

| 写法 | 平台 |
|---|---|
| `owner/repo` 或 `github:owner/repo` | GitHub |
| `codeberg:owner/repo` | Codeberg |
| `codeberg.org/owner/repo` | Codeberg |

新增监控的仓库会在下一次运行时收到一条 “first notification” 消息，之后只在新版本发布时推送。

---

5 开启 Actions 写入权限

进入：

`Settings → Actions → General`

设置：

`Workflow permissions → Read and write permissions`

---

6 运行监控

可以通过两种方式运行：

等待 GitHub Actions 定时执行

手动触发 workflow

本地调试时不发送消息，可以加上环境变量 `DRY_RUN=true`，此时只打印将要发送的内容、不写状态文件：

```bash
TG_BOT_TOKEN=x TG_CHAT_ID=1 DRY_RUN=true python releases-watcher/telegram_watcher.py
```

---

定时任务

默认每 6 小时检查一次：

`cron: "0 */6 * * *"`

为什么是 6 小时：GitHub Actions 的定时触发是“尽力而为”的，实测在 `*/45`（32 次/天）配置下
4.2 天只跑了 16 次（3.8 次/天，成功率 11.9%），而且 15 个间隔里没有一个小于 3.4 小时——
这说明它不是在“随机丢触发”，而是把密集触发压缩到一个约 4 次/天的上限。既然加密不会变快，
就把间隔设到接近这个上限（4 次/天），让成功率接近 100%，同时不浪费触发。

如果你需要比这更快（比如 10 分钟级），只能绕开 Actions 调度器：用外部定时器 POST
`workflow_dispatch`，或把轮询搬到自己的机器上。


---

项目结构
```
releases-watcher
│
├── .github/workflows
│   └── releases-watcher-telegram.yml
│
├── releases-watcher
│   ├── repos.json
│   └── telegram_watcher.py
│
└── .releases-watcher
    └── telegram
        └── owner__repo.txt
```

---

使用场景

适合以下情况：

关注多个 GitHub 开源项目

希望第一时间获得版本更新通知

不想手动频繁查看 Release 页面

希望通过 Telegram 集中接收更新



---

注意事项

支持 GitHub Releases 与 Codeberg Releases（Forgejo API）

探测走 RSS/Atom（不计 API 配额），仅在有变化时调 API，因此配额消耗很小

GitHub Actions 有运行频率限制，定时任务可能被延迟或丢弃



---

License

MIT License

---
