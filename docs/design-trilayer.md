# Design: Psi Python 重构 + TriLayer Agent + Ask 工具

> 脑暴文档 v2（Phase 3，重写版）。确认后再进入 plan/spec 与增量开发。

## Problem

现有 Psi 是 945 行 PowerShell 单文件 harness：OpenAI 兼容 API 客户端（SSE 流式）、8 个工具（read/write/edit/bash/glob/grep/web/web_search）、会话存储、HttpListener + 内嵌 HTML Web UI。单文件已到维护极限，且 agent 只有一条主线，无法分解任务，也没有向用户提问的通道。

目标：用 Python 多文件结构重构，加入 TriLayer Agent 系统（最多 3 层，上层派发、下层严格执行、回复契约明确）与 **ask 工具**（AI 主动发问 + 选项卡片，用户选择/输入/提交）。UI 上每个 subagent 显示为右上角圆形浮窗，点击弹模态框看执行进度。

## Context

- 现有代码：`agent.ps1`（config → 工具 → LLM 流式 → Process-Turn 循环 → Web 服务器，逻辑已全部读懂）；`config.json`（api_key/endpoint/model）；`sessions/*.json`。
- 约束：config.json 与 sessions 格式保持兼容；Windows；git 已有仓库，本地提交不 push。
- 决策（默认）：同仓库共存——新增 Python 包 `yesir/` + `pyproject.toml`，`agent.ps1` 保留为 legacy 参照。

## 三大子系统设计

### 1. TriLayer Agent 系统

#### 方案 T1：固定三层角色（推荐）

```
L1 Orchestrator（唯一面向用户的 agent）
  ├─ 规划、分解、派发；自己也能直接用工具
  └─ spawn 工具 → L2 Task Agent
L2 Task Agent
  ├─ 接收 TaskSpec，独立会话独立上下文，拥有全部 8 工具
  ├─ 可 spawn L3 Worker
  └─ 必须按 reply_format 回复
L3 Worker（最底层）
  ├─ 只做基础任务：单文件操作、单次搜索、单条命令
  ├─ 工具受限（无 spawn，白名单），禁止扩展目标
  └─ 必须按 reply_format 回复
```

#### 方案 T2：递归深度制

不预定义角色，任何 agent 都有 spawn 工具，`depth ≤ 3` 即可，子 agent 人设由父在 TaskSpec 现场描述。

**Pros/Cons**：T1 语义清晰、"越往下越基础"有结构保证，但角色固定；T2 灵活但行为依赖父 agent 现写的 prompt，不稳定。**推荐 T1**——结构性约束只有固定角色守得住。

**派发契约 TaskSpec**：`{goal, reply_format, context, constraints}`。
**严格执行**：下层 system prompt = 层级角色 prompt + TaskSpec + 纪律条款（不得越权、不得扩大范围、最终消息必须符合 reply_format；违反 → 父层判 FAIL 可重派）。
**契约校验**：reply_format 要求结构化字段时做轻量校验，失败让子会话继续修正。

**执行模型**：子 agent = 独立线程 + 独立消息列表，默认父阻塞等待；同层多个 subagent 可并行（父等全部完成汇总）。所有事件进 per-session 事件流供 UI 消费。

### 2. Ask 工具（AI 主动发问）

新增第 9 个工具 `ask_user`：

- 参数：`{question, options?: [{label, description}], allow_custom?}`。
- 行为：agent 调用后**当前回合挂起**，UI 在聊天流里渲染问题卡片（问题文本 + 选项按钮 + 自由输入框 + 提交按钮）；用户点选或输入后提交，答案作为 tool result 回填，回合继续。
- 复用现有 NDJSON 流：新增事件类型 `ask`（下发卡片）与端点 `POST /answer`（回传），`ask_user` 工具内部阻塞在 `threading.Event` 上。零依赖、无轮询。
- 局限（诚实说明）：挂起期间刷新页面会丢失该回合的流（与现状一致——原版回合中途刷新同样丢流）。v1 接受此限制。

**发问权限（关键决策）**：
- **推荐：仅 L1 可问用户**。L2/L3 的提问通道是其父 agent（写在 reply_format 里，如"如有疑问，在回复中列出 OPEN_QUESTIONS"）。理由：层级纪律干净——用户只面对 L1；子 agent 挂起等用户输入会让线程/浮窗状态复杂化。
- 备选：L1+L2 可问（L3 不行），实现上只是权限表开关，浮窗卡片多一个来源标识。

### 3. UI

技术栈两案：
- **方案 A：stdlib 零依赖（推荐）**——`http.server.ThreadingHTTPServer` + 移植内嵌 HTML/JS 到 `web/` 静态文件，NDJSON 流式。无 pip 依赖，双击即跑，前端逻辑可移植，改动集中在新增组件。Cons：HTTP 层手写（原版已趟平）、无 WebSocket（NDJSON 够用）。
- **方案 B：FastAPI + httpx**——async 优雅但引 4+ 依赖，agent 循环是阻塞 I/O，收益低，过度工程。

**浮窗/模态框**：
- 每个 spawn 的 subagent 在右上角生成圆形浮窗（~48px，层级着色：L2 紫、L3 灰），状态点：运行中=呼吸动画，完成=✓，失败=✗；多个纵向堆叠。
- 点击 → 模态框：TaskSpec（goal/reply_format）、实时进度流（工具调用增量渲染）、最终回复（按 reply_format 高亮）、耗时/token。
- **ask 卡片**与浮窗互不打扰；浮窗内嵌 ask 时在浮窗上加"?"角标提示。

## 推荐组合：T1 + A + ask(L1 only)

实现轮廓：
1. `pyproject.toml` + ruff 全套（isort/lint/format），一键检查脚本
2. `yesir/config.py` / `yesir/session.py` —— 兼容现有 config.json 与 sessions
3. `yesir/tools/` —— 8 工具移植 + `ask_user`
4. `yesir/llm.py` —— stdlib SSE 流式客户端（DeepSeek reasoning 兼容）
5. `yesir/agent.py` —— Agent 循环，事件回调制
6. `yesir/trilayer.py` —— TaskSpec、spawn 工具、层级 prompt、契约校验、线程池
7. `yesir/server.py` —— ThreadingHTTPServer：/chat NDJSON + /answer
8. `web/` —— 移植原 UI + 浮窗 + 模态框 + ask 卡片
9. git：每个可运行切片即 commit，不 push

## Open Questions

1. 技术栈：A（推荐）还是 B？
2. 层级语义：T1（推荐）还是 T2？
3. 并行：同层 subagent 允许并行（推荐）还是严格串行？
4. 模型：三层同一 model（推荐，先跑通）还是按层配置？
5. ask 权限：仅 L1（推荐）还是 L1+L2？
