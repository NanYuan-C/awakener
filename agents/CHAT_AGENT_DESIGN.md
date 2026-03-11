# Chat Agent 设计备忘

> 本文档描述如何在现有架构上增加一个对话 Agent（chat agent）。
> 不需要改动现有模块的核心逻辑，只需新增文件并接入已有基础设施。

## 架构定位

```
agents/
├── engine.py          ← 共用：LLM ↔ 工具循环
├── tools/             ← 共用：工具注册表 + 执行器
├── activator/         ← 已有：循环 Agent
├── auditor/           ← 已有：审计 Agent
└── chat/              ← 新增：对话 Agent
```

Chat agent 和 activator 本质相同——都是调用 `engine.run_round()`，区别在于：

| 维度 | Activator | Chat Agent |
|------|-----------|------------|
| 触发方式 | 定时器自动唤醒 | 用户发送消息 |
| 提示词 | persona + rules + snapshot | 专用的 chat persona（如：帮用户构建提示词） |
| 工具集 | shell / read / write / edit | 可定制（如：只给 read + write 用于编辑提示词） |
| 上下文 | 历史 round 摘要 + 灵感 | 当前会话的聊天记录 |
| 生命周期 | 一直跑，轮次间隔等待 | 用户发一条，回一条 |

## 需要新增的文件

### 1. `agents/chat/__init__.py`

```python
"""Chat Agent — 对话式交互"""
```

### 2. `agents/chat/context.py`

负责组装 chat agent 的 system message。

```python
def build_chat_system_message(project_dir: str) -> str:
    """
    加载 chat 专用 persona（如 prompts/chat.md），
    附加可用工具说明。
    不需要 snapshot、不需要 lessons。
    """
    ...
```

关键点：
- 提示词直接放在 `agents/chat/persona.md`，统一英文，无需模板/复制/i18n
  - chat agent 的提示词是系统内部使用，用户不需要编辑，英文即可
  - 与 activator 不同：activator 的提示词用户会直接修改，所以提供中英文两套预写模板，初始化时按语言选择复制哪套
- 不注入 activator 的 snapshot / timeline / memory
- 工具文档只列出 chat agent 有权使用的工具

### 3. `agents/chat/session.py`

会话管理 + 聊天记录存储。

```python
class ChatSession:
    session_id: str
    messages: list[dict]       # 标准 role/content 格式
    created_at: str
    
    def add_user_message(self, text: str) -> None: ...
    def add_assistant_message(self, text: str) -> None: ...
    def get_messages(self) -> list[dict]: ...
    def save(self) -> None: ...
    
    @staticmethod
    def load(session_id: str) -> "ChatSession": ...
```

存储建议：
- 简单方案：`data/chat/{session_id}.json`，每个会话一个文件
- 每次对话追加 message，不需要 JSONL（会话不会太大）

### 4. `api/routes/chat.py`（新路由文件）

```python
# POST /api/chat/send        — 发送消息，流式返回回复
# GET  /api/chat/sessions     — 列出会话
# GET  /api/chat/sessions/{id} — 获取会话历史
# DELETE /api/chat/sessions/{id} — 删除会话
```

核心流程（POST /api/chat/send）：
1. 接收 `{ session_id?, message }` 
2. 加载或创建 ChatSession
3. `build_chat_system_message()` 组装 system prompt
4. 把 session.messages 作为上下文
5. 调用 `engine.run_round(messages, tool_executor, ...)`
6. 通过 WebSocket 流式推送思考过程和回复
7. 保存 assistant 回复到 session

### 5. 前端文件

- `web/templates/chat.html` — 聊天页面
- `web/js/chat.js` — WebSocket 监听 + 消息渲染
- `api/app.py` — 注册 `/chat` 页面路由

## 需要修改的现有文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `api/app.py` | 加页面路由 | `@app.get("/chat")` 渲染 chat.html |
| `api/routes/__init__.py` | 引入 chat router | `from api.routes.chat import chat_router` |
| `web/templates/base.html` | 侧边栏加链接 | 加一个 Chat 菜单项 |
| `agents/tools/__init__.py` | 无需改 | 注册表已支持按需获取 |

## 工具权限控制

Chat agent 不应该有 activator 的全部工具权限。建议：

在 `agents/tools/__init__.py` 中增加按 scope 过滤：

```python
def get_tools_schema(scope: str = "all") -> list[dict]:
    """
    scope="all"  → 返回全部工具（activator 用）
    scope="chat" → 只返回 chat agent 允许的工具
    """
```

或者更简单：chat 路由调用 `run_round()` 时传入一个只包含特定工具的 schema 列表。

## WebSocket 复用

当前 WebSocket 是广播模式（所有连接收到所有消息）。Chat agent 需要定向推送：

- 方案 A：消息加 `source` 字段区分（`source: "activator"` / `source: "chat"`），前端按 source 过滤
- 方案 B：创建 `api/ws/stream.py`（StreamManager），支持按 channel 订阅

方案 A 改动最小，推荐先用 A。

## 不需要改的部分

- `core/` — 配置、LLM、日志，全部复用
- `agents/engine.py` — run_round() 直接复用
- `agents/tools/executor.py` — ToolExecutor 直接复用
- `agents/activator/` — 完全不动
- `agents/auditor/` — 完全不动
- `services/` — memory / skills / init 不涉及
