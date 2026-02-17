# Slack-Booty

A personal AI agent that runs on a Mac Mini, communicates through Slack, and learns new skills on the fly. It uses a hybrid LLM strategy — a locally-hosted model (Ollama) for simple tasks and the Claude API for complex conversations — with automatic fallback and mid-conversation escalation.

## Features

- **Slack Socket Mode** — no public URL, port forwarding, or firewall changes needed
- **Hybrid LLM routing** — per-skill defaults, dynamic escalation after N turns, global override, automatic local-to-cloud fallback
- **Dynamic skills** — YAML-based configs you can create by just telling the bot what you want
- **Scheduled tasks** — cron-based skill triggers with persistent job storage (survives restarts)
- **Conversation memory** — full SQLite-backed history for context, resumption, and review
- **Output export** — saves session transcripts as markdown or text files

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.com) installed and running
- A Slack workspace where you can create apps
- An [Anthropic API key](https://console.anthropic.com)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/kevlandsman/slack-boot.git
cd slack-boot
pip install -r requirements.txt
```

### 2. Install the local model

```bash
ollama pull qwen3:8b
```

This downloads the Qwen 3 8B model (~5-6 GB). It fits comfortably on a 16GB Mac Mini with room to spare. If you'd prefer a smaller model, `qwen3:4b` works too — just update `config.yaml`.

### 3. Create the Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** > **From scratch**
2. Name it whatever you like (e.g., "Booty") and select your workspace

#### Enable Socket Mode

3. Go to **Settings > Basic Information > App-Level Tokens**
4. Click **Generate Token and Scopes**, name it (e.g., "socket"), and add the `connections:write` scope
5. Copy the `xapp-` token — this is your **app token**

#### Add bot permissions

6. Go to **Features > OAuth & Permissions > Scopes > Bot Token Scopes** and add:

| Scope | Purpose |
|---|---|
| `chat:write` | Send messages |
| `im:read` | Read DMs to the bot |
| `im:write` | Open and send DMs |
| `im:history` | Access DM history for context |
| `channels:read` | List channels |
| `channels:history` | Read messages in joined channels |
| `users:read` | Look up user names and IDs |
| `files:write` | Share files (grocery lists, summaries, etc.) |

#### Enable events

7. Go to **Features > Event Subscriptions** and toggle **Enable Events** on
8. Under **Subscribe to bot events**, add:
   - `message.im`
   - `message.channels`
   - `app_mention`

#### Install to workspace

9. Go to **Settings > Install App** and click **Install to Workspace**
10. Copy the `xoxb-` token — this is your **bot token**

### 4. Configure

Edit `config.yaml` in the project root:

```yaml
slack:
  bot_token: "xoxb-your-bot-token"
  app_token: "xapp-your-app-level-token"

claude:
  api_key: "sk-ant-your-api-key"
  model: "claude-haiku-4-20250414"

ollama:
  base_url: "http://localhost:11434"
  model: "qwen3:8b"

# Optional: your Slack user ID for startup notifications
owner_user_id: "U0123ABCDEF"
```

To find your Slack user ID: click your profile picture in Slack > **Profile** > **More** (three dots) > **Copy member ID**.

### 5. Run

```bash
python main.py
```

The bot will connect to Slack and send you a startup DM (if `owner_user_id` is set):

> Back online. 3 skill(s) active, next scheduled skill: daily-checkin.

## Usage

### Talk to it

DM the bot or mention it in a channel. It responds to general questions using the local model by default.

### Create skills by talking

Tell the bot what you want and it generates a YAML skill config automatically:

> "Please check in with me every day at 4 PM"

The bot creates a skill, registers the schedule, and confirms back to you. You can refine it:

> "Add a question about exercise"
> "Change it to 5 PM"

### Built-in example skills

Three example skills are installed to `~/.slack-booty/skills/`:

| Skill | Trigger | What it does |
|---|---|---|
| `daily-checkin` | Scheduled (4 PM daily) | DMs you 2-3 questions about your day, follows up on interesting answers |
| `meal-planning` | Mention in #meal-planning | Helps plan weekly dinners collaboratively |
| `grocery-list` | Command in #meal-planning | Converts the latest meal plan into a grouped grocery list |

### Write your own skills

Create a YAML file in `~/.slack-booty/skills/`:

```yaml
name: standup-summary
description: Summarize daily standup messages
trigger: command
channel: "#engineering"
llm: local

context: |
  Summarize the standup updates from today's messages.
  Group by person. Highlight any blockers.

output:
  format: markdown
  save_to: ~/standups/{date}.md
  post_to_channel: true
```

#### Skill config reference

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Kebab-case identifier |
| `description` | Yes | What the skill does |
| `trigger` | Yes | `scheduled`, `mention`, or `command` |
| `context` | Yes | System prompt for the LLM |
| `channel` | No | `dm` or `#channel-name` |
| `schedule` | If scheduled | Cron expression, e.g. `0 16 * * *` |
| `target_user` | No | Username for DM skills |
| `llm` | No | `local` or `cloud` (default: `local`) |
| `escalation_threshold` | No | Turns before escalating to cloud (default: 4) |
| `max_turns` | No | Max conversation turns (default: 8) |
| `fixed_questions` | No | Questions to always ask |
| `rotating_questions` | No | Questions to rotate through |
| `participants` | No | List of usernames |
| `output.format` | No | `markdown` or `text` |
| `output.save_to` | No | File path with `{date}` or `{week}` placeholders |
| `output.post_to_channel` | No | Post output back to the channel |

## LLM routing

The bot picks which LLM handles each message using three levels of config:

1. **Per-skill default** — set `llm: local` or `llm: cloud` in the skill YAML
2. **Dynamic escalation** — if a conversation exceeds `escalation_threshold` turns, it switches to cloud mid-conversation (the user sees no interruption)
3. **Global override** — set `llm_override: cloud` in `config.yaml` to force all traffic to one provider

If Ollama is down or errors out, the bot automatically falls back to Claude.

## Running as a service (launchd)

To keep the bot running in the background and auto-start on boot, create `~/Library/LaunchAgents/com.slack-booty.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.slack-booty</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/slack-boot/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/slack-boot</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/slack-booty.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/slack-booty.stderr.log</string>
</dict>
</plist>
```

Update the paths, then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.slack-booty.plist
```

## Project structure

```
slack-booty/
├── main.py                  # Entry point
├── config.yaml              # API keys, model settings
├── requirements.txt         # Dependencies
├── agent/
│   ├── core.py              # Central orchestrator
│   ├── router.py            # Message classification
│   ├── llm_router.py        # Hybrid LLM provider selection
│   ├── scheduler.py         # APScheduler + cron job management
│   └── state.py             # SQLite conversation state
├── skills/
│   ├── loader.py            # YAML skill parser
│   ├── executor.py          # Skill conversation engine
│   ├── creator.py           # Natural language → YAML generator
│   └── output.py            # File/channel output handlers
├── providers/
│   ├── ollama.py            # Local model client
│   └── claude.py            # Anthropic API client
├── slack/
│   ├── bot.py               # Bolt app + Socket Mode
│   └── handlers.py          # Event handlers
├── db/
│   └── schema.sql           # SQLite schema
└── tests/                   # 87 tests
```

## Tests

```bash
pip install pytest pytest-asyncio
python -m pytest tests/ -v
```

## Data locations

| What | Where |
|---|---|
| Database | `~/.slack-booty/slack-booty.db` |
| Logs | `~/.slack-booty/slack-booty.log` |
| Skills | `~/.slack-booty/skills/*.yaml` |
| Check-in exports | `~/checkins/{date}.md` |
| Meal plans | `~/meal-plans/{week}.md` |
| Grocery lists | `~/grocery-lists/{date}.md` |
