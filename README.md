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
2. 调用 GitHub API（`api.github.com`）或 Codeberg API（`codeberg.org/api/v1`）获取最新 Release
3. 与本地记录的版本进行比较
4. 如果发现新版本，则发送 Telegram 通知
5. 将最新版本写入状态文件，避免重复通知

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

默认每 45 分钟检查一次：

`cron: "*/45 * * * *"`

你可以根据需要修改检查频率。


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

依赖 GitHub API / Codeberg API，都会被限流

GitHub Actions 有运行频率限制



---

License

MIT License

---
