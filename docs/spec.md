# Spec: YESIR（TriLayer + Inquire）

> 项目定位（2026-09-01 用户决策）：不再是 Psi 的新版，而是以 TriLayer + Inquire 机制为核心的独立项目，命名 YESIR。Psi（PowerShell）保留为前作。

> 配套 `docs/design-trilayer.md`（已确认：A stdlib / T1 固定三层 / 允许并行 / 三层同一 model / 仅 L1 可问）。

## 1. 包结构

```
pyproject.toml            # 项目元数据 + ruff 配置
yesir/
  __init__.py             # 版本号
  __main__.py             # 入口：python -m yesir [query] | python -m yesir --web [port]
  config.py               # Config dataclass + 加载（config.json > env）
  llm.py                  # OpenAI 兼容 SSE 流式客户端（stdlib urllib）
  events.py               # Sink 协议 + 控制台 Sink + 流式聚合
  session.py              # 会话存储（兼容 sessions/*.json 旧格式）
  agent.py                # Agent 主循环（工具调度、事件发射）
  trilayer.py             # TaskSpec、层级 prompt、spawn 工具、契约校验、线程编排
  server.py               # ThreadingHTTPServer + 路由
  tools/
    __init__.py           # 注册表：TOOL_DEFS / TOOL_IMPLS / 白名单
    files.py              # read / write / edit
    shell.py              # bash（subprocess + cmd /c + UTF-8）
    search.py             # glob / grep
    webtools.py           # web / web_search
    ask.py                # ask_user（仅 L1）
web/
  index.html              # 从 agent.ps1 移植 + 新组件
  app.js                  # 会话/流式/浮窗/模态框/ask 卡片
  style.css
tests/
  test_trilayer.py        # FakeLLM 驱动的编排契约测试
  test_session.py
  test_tools.py
```

## 2. 核心契约

### 2.1 Event Sink（`events.py`）

所有 agent（含子 agent）通过 Sink 发事件，UI 与控制台是两种 Sink 实现。

```python
class Sink(Protocol):
    def emit(self, type: str, content: Any) -> None: ...
```

主回合事件沿用原版 NDJSON 类型：
`text` / `newline` / `reasoning_start` / `reasoning` / `reasoning_end` / `tool` / `tool_result` / `error` / `sessionId` / `done`

新增类型：
| type | content | 说明 |
|---|---|---|
| `agent_spawn` | `{id, layer, goal, reply_format, parent_id}` | 子 agent 已创建，UI 生成浮窗 |
| `agent_status` | `{id, status: running\|done\|failed\|waiting_parent}` | 浮窗状态点切换 |
| `agent_event` | `{id, event: {type, content}}` | 子 agent 的内部事件转发（进度流） |
| `ask` | `{id, question, options: [{label, description?}], allow_custom}` | 挂起主回合，UI 渲染问题卡片 |

并发规则：NDJSON 流单写者——Web Sink 内部持锁；子 agent 事件经父的 Sink 包一层 `agent_event`。

### 2.2 TaskSpec 与 spawn 工具（`trilayer.py`）

```python
@dataclass
class TaskSpec:
    id: str            # "a" 短随机 id
    layer: int         # 2 或 3
    goal: str          # 做什么
    reply_format: str  # 怎么交差（自然语言描述，如 "是/否 + 理由"）
    context: str       # 父给的背景材料
    constraints: str   # 边界约束（可空）
    parent_id: str | None
```

`spawn` 工具 schema（L1 与 L2 各持一份，layer 参数由注册时固化）：
```json
{"name": "spawn",
 "parameters": {"goal": "str, required", "reply_format": "str, required",
                "context": "str, optional", "constraints": "str, optional"}}
```

- L1 调用 → 派发 L2；L2 调用 → 派发 L3；L3 无 spawn（不在工具表）。
- 返回值（tool result）：子 agent 最终回复原文；失败时返回 `FAIL: <原因>`，父层可重派。
- **契约校验**：若 `reply_format` 含 "JSON"（大小写不敏感），对子 agent 最终消息做 `json.loads`；失败 → 向子会话注入一条修正消息让其重答，最多重试 2 次，仍失败则原样返回并附警告。
- **严格纪律**（写进 L2/L3 system prompt）：只做 goal 内的事；不得修改目标/扩大范围；工具输出即事实，不得编造；最终消息必须严格符合 reply_format；遇到无法完成的情况，按 reply_format 报告失败而不是自由发挥。

### 2.3 层级角色（prompt 要点）

- **L1 Orchestrator**：基础编码 prompt（沿用原版）+ 拆解/派发指引 + spawn 用法 + "你是唯一能向用户提问的层"。
- **L2 Task Agent**：任务执行者；拥有全部 9 工具；接到 TaskSpec 后独立完成；可 spawn L3 处理基础子步骤。
- **L3 Worker**：基础工人；工具白名单 `read/write/edit/glob/grep/bash`（无 web_search/web/ask/spawn——web 类留给上层聚合）；单步操作为主。

### 2.4 ask_user 工具（`tools/ask.py`）

```json
{"name": "ask_user",
 "parameters": {"question": "str, required（单问）",
                "options": {"type": "array", "items": {"label": "str", "description": "str?"}, "required": false},
                "allow_custom": "bool, optional (default true)",
                "questions": {"type": "array", "items": {"question": "str", "options": "array?", "allow_custom": "bool?"}, "required": false}}}
```

- 单问用 `question`（+可选 `options`/`allow_custom`）；多问用 `questions` 数组，每项可自带 `options`（缺省无选项=纯文本输入）与 `allow_custom`（缺省继承顶层，默认 true）。
- 行为：生成 `ask` 事件 → 在 `PendingAsk` 注册表登记 → `threading.Event.wait()` 阻塞（期间每 15s 向 sink 发 `ping` 保活，防止浏览器掐断静默流）→ UI `POST /answer {id, value}` → 唤醒 → 返回 `"USER: <value>"`（多问时 `value` 为数组，结果格式化为 `USER:\n1. ...\n2. ...`）。
- 超时 300s，超时返回 `"ERROR: 用户未回答"`。
- 事件 content 统一归一化为 `{id, questions: [{question, options: [{label, description?}], allow_custom}]}`。
- 持久化：每条 ask 结束（回答或超时）时通过回调记入 `TriLayer.asks`（`{id, questions, answers, status}`），随会话落盘（session `asks` 字段）；UI 重进/刷新后以已答卡片回放。
- 仅 L1 工具表含此工具（在 `TriLayer.build_orchestrator` 以 BoundTool 挂载）。

### 2.5 LLM 客户端（`llm.py`）

- `stream_chat(messages, tool_defs, on_delta) -> LLMResult`，`LLMResult = {content, tool_calls, reasoning}`。
- stdlib `urllib.request` POST，逐行读 SSE（`data: ` 前缀 / `[DONE]`），兼容 DeepSeek `reasoning_content`。
- tool_calls 按 index 增量拼接（与原 ps1 相同）。
- 三层同一 model：`Config.model`。

### 2.6 Server 端点（`server.py`）

沿用原版全部端点：`GET /`（静态文件）、`/model`、`/config-status`、`POST /configure`、`POST /chat`（NDJSON 流）、`GET /sessions`、`GET /session?id=`、`POST /save`、`POST /new`、`DELETE /session?id=`、`POST /pickfile`。

新增：`POST /answer` `{id, value}` → 唤醒对应 PendingAsk，200/404。

静态文件从 `web/` 目录读取（不再内嵌字符串）。

### 2.7 线程模型

- 每个HTTP 请求在 ThreadingHTTPServer 线程中处理；`/chat` 的整回合（含子 agent）在该线程内推进。
- spawn：为每个 TaskSpec 起 `Thread(target=run_agent)`，多个 spawn 并行；父在全部 join 后继续（工具结果按 tool_call 顺序回填）。
- 子 agent 共享父的 Sink（包装为 agent_event）；各自持有独立消息列表与会话内存（不落盘，最终结果进父消息流，随父会话一起存储）。
- 子 agent 上限：每回合 ≤ 8 个 spawn，超出报错。

## 3. UI 契约（`web/`）

- 保留原版全部功能：会话侧栏（增删改名搜索）、NDJSON 流式渲染、reasoning 折叠、工具块、配置弹窗、文件浏览、智能滚动。
- **浮窗**：`agent_spawn` → 右上角生成 48px 圆形浮窗，纵向堆叠；L2 紫 / L3 灰边；状态点由 `agent_status` 驱动（running=呼吸动画、done=✓、failed=✗）；点击开模态框。
- **模态框**：TaskSpec 摘要（goal/reply_format）、实时进度（按 `agent_event` 增量追加工具行与文本）、最终回复、关闭按钮；`agent_event` 到达时若模态框开着则实时刷新。
- **ask 卡片**：`ask` 事件 → 聊天流内插入卡片（问题 + 选项按钮 + 可选输入框 + 提交）；点击选项或提交输入 → `POST /answer` → 卡片变为已回答态（选中项高亮）。回合期间只允许一张活动卡片。
- 会话切换/刷新后浮窗从会话消息中的 spawn 记录重建为终态（✓/✗）。

## 4. 工程约束

- Python ≥ 3.13，仅标准库。
- ruff：lint（E/W/F/I/N/UP/B/C4/SIM/RUF 等宽选集）+ format；`scripts/check.ps1` 一键 `ruff check --fix && ruff format && ruff check`。
- 每个任务完成即 `git commit`（本地，永不 push）。
- `config.json` / `sessions/` 保持 gitignore；新密钥不入库。
- 测试：pytest 仅覆盖可脱网验证的核心契约（FakeLLM 编排、会话、纯函数工具）；真实 API 只做冒烟，不入测试。
