<p align="center">
  <h1 align="center">Awakener</h1>
  <p align="center">
    <strong>给 AI 一台服务器，让它自由生长</strong>
  </p>
  <p align="center">
    轻量级自主 Agent 平台 · 支持所有主流 LLM
  </p>
  <p align="center">
    <a href="README.md">English</a> · <strong>中文</strong>
  </p>
</p>

---

## 什么是 Awakener？

Awakener 是一个**自主 AI Agent 运行平台**。给它一个 LLM API Key 和一台服务器，它就会持续运行——自主探索、构建、学习。

Agent 在你的服务器上拥有自己的家目录，可以读写文件、执行 Shell 命令、维护长期项目。它按设定的间隔醒来工作，你通过 Web 管理后台随时查看。

## 核心功能

### Agent 运行时
- 按设定间隔激活，执行工具调用循环，然后休眠
- **按天计轮次** — 每天从第 1 轮开始，Agent 以"今天"为单位思考和规划
- **今日动态注入** — 每次唤醒时注入今天已完成的轮次摘要，避免重复劳动
- **经验教训**（`LESSONS.md`）— Agent 跨轮次积累实用经验，每轮都会注入提示词
- **系统快照** — 由独立 LLM 审计员在每轮后自动维护的资产清单（服务、项目、文件等）

### 人设与规则
两个可在管理后台直接编辑的提示词文件：
- `prompts/persona.md` — Agent 的性格、目标、行为风格
- `prompts/rules.md` — 行为约束和操作规范

### 技能系统
以标准化 Markdown 包的形式安装专业知识。采用渐进式披露——只在需要时才加载完整指令。技能存放在 Agent 的家目录下，Agent 可以自行管理。

### Agent 家目录
Agent 拥有结构化的家目录（默认 `/home/agent`），首次运行时自动从模板初始化：
- `LESSONS.md` — 经验日志，每轮注入提示词
- `skills/` — 已安装的技能包

### 实时观察面板
- WebSocket 实时推送日志流
- 一键启动 / 停止
- 活动动态时间线，支持标签过滤
- 每轮完整详情查看

### 隐身系统
五层保护让 Awakener 对 Agent 完全不可见——路径隐匿、命令拦截、输出过滤、关键词净化、环境变量清理。Agent 不会收到任何 `[BLOCKED]` 提示，它根本不知道这个平台的存在。

## 快速开始

### 环境要求
- Linux 服务器，Python 3.10+
- 任意 LLM 提供商 API Key（OpenAI、Anthropic、DeepSeek、Gemini 等）

### 安装

```bash
# 一键安装
curl -fsSL https://raw.githubusercontent.com/NanYuan-C/awakener/main/install.sh | bash

# 或手动安装
git clone https://github.com/NanYuan-C/awakener.git /opt/awakener
cd /opt/awakener
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

启动后访问 `http://你的服务器IP:9120`，在**设置**页面配置模型、API Key 和 Agent 参数。

### 后台运行

```bash
tmux new -s awakener
cd /opt/awakener && source venv/bin/activate && python app.py
# Ctrl+B 然后 D 脱离会话
```

## 配置说明

### 模型配置

在设置页面填写提供商、模型名称、API 地址和 API Key。Awakener 通过 [LiteLLM](https://docs.litellm.ai/docs/providers) 支持所有主流提供商（OpenAI、Anthropic、DeepSeek、Gemini、OpenRouter 等）。

快照审计员可以单独指定一个更轻量的模型，只需填写模型名称，提供商自动继承。

### Agent 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 激活间隔 | 60 秒 | 两轮之间的等待时间，0 = 连续运行 |
| 工具预算 | 30 次/轮 | 每轮最多调用工具次数 |
| 命令超时 | 120 秒 | Shell 命令最大执行时间 |
| 历史轮次 | 3 轮 | 注入为对话历史的最近轮次数 |

## Agent 工具集

| 工具 | 说明 |
|------|------|
| `shell_execute` | 执行 Shell 命令 |
| `read_file` | 读取文件 |
| `write_file` | 写入 / 追加文件 |
| `edit_file` | 查找替换编辑文件 |
| `skill_read` | 读取技能文档 |
| `skill_exec` | 执行技能脚本 |

## 项目结构

```
awakener/
├── app.py                   # 入口文件
├── install.sh               # 安装脚本
├── config.yaml.example      # 配置模板
├── prompts/
│   ├── persona.md.example   # Agent 人设模板
│   └── rules.md.example     # Agent 规则模板
├── home_template/           # Agent 家目录模板
│   ├── LESSONS.md
│   └── skills/
├── activator/               # Agent 引擎
│   ├── loop.py              # 主激活循环
│   ├── agent.py             # LLM 交互与工具调用
│   ├── tools.py             # Agent 工具
│   ├── context.py           # 提示词组装
│   ├── snapshot.py          # 系统快照审计
│   ├── memory.py            # 时间线与每日动态
│   ├── home_init.py         # Agent 家目录初始化
│   └── stealth.py           # 隐身保护
└── server/                  # Web 管理后台
    ├── main.py
    ├── routes.py
    ├── config.py
    ├── manager.py
    ├── auth.py
    └── websocket.py
```

## 开源协议

[Apache License 2.0](LICENSE)

---

<p align="center">
  <sub>给 AI 一台服务器，看它能创造什么。</sub>
</p>
