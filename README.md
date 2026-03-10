<p align="center">
  <h1 align="center">Awakener</h1>
  <p align="center">
    <strong>Give an AI a server. Watch it grow.</strong>
  </p>
  <p align="center">
    Lightweight autonomous agent platform · Works with all major LLMs
  </p>
  <p align="center">
    <strong>English</strong> · <a href="README_CN.md">中文</a>
  </p>
</p>

---

## What is Awakener?

Awakener is an **autonomous AI agent runtime**. Give it an LLM API key and a server, and it runs continuously — exploring, building, and learning on its own.

The agent has its own home directory, can read and write files, run shell commands, and maintain long-running projects. It wakes up at a set interval, does work, and you check in via the web console.

## Core Features

### Agent Runtime
- Activates at configurable intervals, runs a tool-calling loop, then sleeps
- **Daily round counter** — resets to Round 1 each day, so the agent thinks in day-scoped units
- **Today's activity injection** — each wake-up includes a summary of completed rounds today, preventing redundant work
- **Lessons Learned** (`LESSONS.md`) — the agent accumulates hard-won lessons across rounds, injected into every prompt
- **System Snapshot** — an LLM-audited asset inventory (services, projects, files) kept up to date after each round

### Persona & Rules
Two editable prompt files, configurable from the web console:
- `prompts/persona.md` — who the agent is (character, goals, style)
- `prompts/rules.md` — behavioral constraints and operational guidelines

### Skill System
Install expert knowledge as standardized Markdown packages. Skills use progressive disclosure — full instructions load only when needed. Skills live in the agent's home directory so the agent can manage them itself.

### Agent Home Directory
The agent has a structured home directory (`/home/agent` by default). On first run, Awakener initializes it from a template:
- `LESSONS.md` — experience log, injected into every prompt
- `skills/` — installed skill packages

### Live Dashboard
- Real-time log streaming via WebSocket
- Start / stop / status monitoring
- Activity feed with per-round summaries and tags
- Timeline view with full round details

### Stealth System
Five layers of protection keep Awakener invisible to the agent — path cloaking, command interception, output filtering, keyword scrubbing, and environment sanitization. The agent never sees `[BLOCKED]` messages; it simply doesn't know the platform exists.

## Quick Start

### Requirements
- Linux server, Python 3.10+
- Any LLM provider API key (OpenAI, Anthropic, DeepSeek, Gemini, etc.)

### Installation

```bash
# One-click install
curl -fsSL https://raw.githubusercontent.com/NanYuan-C/awakener/main/install.sh | bash

# Or manually
git clone https://github.com/NanYuan-C/awakener.git /opt/awakener
cd /opt/awakener
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Visit `http://your-server-ip:9120`. Configure model, API key, and agent parameters in the **Settings** page.

### Running in Background

```bash
tmux new -s awakener
cd /opt/awakener && source venv/bin/activate && python app.py
# Ctrl+B then D to detach
```

## Configuration

### Model Setup

Enter provider, model name, API URL, and API key in Settings. Awakener uses [LiteLLM](https://docs.litellm.ai/docs/providers) internally, supporting all major providers (OpenAI, Anthropic, DeepSeek, Gemini, OpenRouter, and more).

The snapshot auditor can use a separate (lighter) model — just enter the model name and it inherits the same provider.

### Agent Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Activation interval | 60s | Wait between rounds. 0 = continuous |
| Tool budget | 30/round | Max tool calls per round |
| Command timeout | 120s | Max shell command execution time |
| History rounds | 3 | Recent rounds injected as conversation history |

## Agent Toolset

| Tool | Description |
|------|-------------|
| `shell_execute` | Run shell commands |
| `read_file` | Read files |
| `write_file` | Write / append files |
| `edit_file` | Find-and-replace file editing |
| `skill_read` | Read skill documentation |
| `skill_exec` | Execute skill scripts |

## Project Structure

```
awakener/
├── app.py                   # Entry point
├── install.sh               # Installation script
├── config.yaml.example      # Configuration template
├── prompts/
│   ├── persona.md.example   # Agent persona template
│   └── rules.md.example     # Agent rules template
├── home_template/           # Agent home directory template
│   ├── LESSONS.md
│   └── skills/
├── activator/               # Agent engine
│   ├── loop.py              # Main activation loop
│   ├── agent.py             # LLM interaction & tool calling
│   ├── tools.py             # Agent tools
│   ├── context.py           # Prompt assembly
│   ├── snapshot.py          # System snapshot auditor
│   ├── memory.py            # Timeline & daily feed
│   ├── home_init.py         # Agent home initialization
│   └── stealth.py           # Stealth protection
└── server/                  # Web management console
    ├── main.py
    ├── routes.py
    ├── config.py
    ├── manager.py
    ├── auth.py
    └── websocket.py
```

## License

[Apache License 2.0](LICENSE)

---

<p align="center">
  <sub>Give an AI a server. See what it creates.</sub>
</p>
