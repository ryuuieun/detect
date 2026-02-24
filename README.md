# OU IST 募集要项检测

用于检测“大阪大学大学院 情报科学研究科”入试页面是否发布了新一年度募集要项。

## 文件

- `/Users/ryuuieun/codex/check_ou_ist_guidelines.py`
- `/Users/ryuuieun/codex/run_ou_ist_check_notify.sh`
- `/Users/ryuuieun/codex/com.ryuuieun.ouistcheck.plist`

## 快速使用

```bash
python3 /Users/ryuuieun/codex/check_ou_ist_guidelines.py --print-json
```

默认会检测：

- `https://www.ist.osaka-u.ac.jp/japanese/examinees/admission/`

默认目标年度是“当前年份 + 1”。例如在 2026 年运行时默认检测 `2027年度`。

## 常用参数

- `--target-year 2027`：手动指定目标年度
- `--state /path/to/state.json`：指定状态文件路径
- `--url <URL>`：追加检测页面（可重复）
- `--alert-on-first-run`：首次运行也对当前已存在条目触发检测
- `--print-json`：输出 JSON 便于自动化处理

## 退出码

- `0`: 未检测到新发布
- `2`: 检测到疑似新发布（目标年度命中或新增条目）
- `1`: 抓取失败且没有可用结果

## 定时任务示例（每天 09:00）

```bash
0 9 * * * /usr/bin/python3 /Users/ryuuieun/codex/check_ou_ist_guidelines.py --target-year 2027 >> /tmp/ou_ist_check.log 2>&1
```

## macOS 定时 + 通知（推荐）

先赋予脚本执行权限：

```bash
chmod +x /Users/ryuuieun/codex/run_ou_ist_check_notify.sh
```

将 `plist` 安装到 LaunchAgents 并加载：

```bash
mkdir -p ~/Library/LaunchAgents
cp /Users/ryuuieun/codex/com.ryuuieun.ouistcheck.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.ryuuieun.ouistcheck.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.ryuuieun.ouistcheck.plist
```

手动触发一次测试：

```bash
launchctl start com.ryuuieun.ouistcheck
```

停止定时任务：

```bash
launchctl unload ~/Library/LaunchAgents/com.ryuuieun.ouistcheck.plist
```

## 通知方式

- 默认：macOS 系统通知（检测到新年度或抓取失败时）
- 可选：Webhook 通知（如 Slack/企业微信机器人等）

使用 webhook 时，先设置环境变量再运行脚本：

```bash
export OU_IST_WEBHOOK_URL='https://example.com/your-webhook'
/Users/ryuuieun/codex/run_ou_ist_check_notify.sh
```

## GitHub Actions + Telegram 通知

工作流文件：

- `/Users/ryuuieun/codex/.github/workflows/ou-ist-check.yml`

状态文件（由 Action 自动更新并提交）：

- `/Users/ryuuieun/codex/.github/state/ou_ist_guidelines_state.json`

通知脚本：

- `/Users/ryuuieun/codex/notify_ou_ist.py`

### 行为说明

- 每天 `09:00 JST` 定时运行（`00:00 UTC`）
- 抓取页面并输出 `summary.json`
- 自动更新状态文件并提交回仓库（保证后续“新增检测”有效）
- 在以下情况发送通知：
  - 检测到目标年度募集要項
  - 抓取失败（fetch error）
  - 心跳消息（无更新时也会每日发送一次）
- Telegram 发送采用重试机制（默认 3 次），且通知失败不会使主检查任务失败

### 需要配置的 Secrets

Telegram（必需）：

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

可选环境变量（在 workflow 中）：

- `HEARTBEAT_NOTIFY`
  - `1`（默认）：无更新时也发送心跳
  - `0`：仅在“检测到更新/抓取失败”时通知

### Telegram 参数获取

1. 在 Telegram 中联系 `@BotFather` 创建 bot，拿到 token。  
2. 给 bot 发一条消息。  
3. 访问：`https://api.telegram.org/bot<你的token>/getUpdates`，在返回 JSON 里找到 `chat.id`，即 `TELEGRAM_CHAT_ID`。
