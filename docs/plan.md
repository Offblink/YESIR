# Implementation Plan: OKSIR（TriLayer + Inquire）

> Design: `docs/design-trilayer.md`（已确认）｜Spec: `docs/spec.md`

## Component Map

NEW: `pyproject.toml`, `scripts/check.ps1`, `oksir/*`（9 模块）, `web/{index.html,app.js,style.css}`, `tests/{test_trilayer,test_session,test_tools}.py`
MODIFIED: 无（`agent.ps1` 保持 legacy 不动）
DELETED: 无

## Tasks

### Task 1: 脚手架 + ruff 工具链
**What:** pyproject（元数据 + ruff lint/format 配置）、包骨架、check 脚本。
**Files:** `pyproject.toml`, `oksir/__init__.py`, `oksir/__main__.py`（占位 arg 解析）, `scripts/check.ps1`
**Acceptance:** `ruff check .` 与 `ruff format --check .` 通过；`python -m oksir --help` 打印用法。
**Depends:** none

### Task 2: config + session（兼容旧格式）
**What:** Config 加载（config.json > env）；会话列表/读写删（沿用旧 JSON schema）。
**Files:** `oksir/config.py`, `oksir/session.py`, `tests/test_session.py`
**Acceptance:** 加载真实 `config.json` 得到 endpoint/model；对现有 `sessions/20260827-*.json` 能 list/load；pytest 通过。
**Depends:** 1

### Task 3: 8 个基础工具移植
**What:** files（read 含 `:N-M` 选择器/write/edit）/ shell（bash, cmd /c + UTF-8 + 超时）/ search（glob/grep）/ webtools（web/web_search）+ 注册表与工具白名单结构。
**Files:** `oksir/tools/{__init__,files,shell,search,webtools}.py`, `tests/test_tools.py`
**Acceptance:** 对真实文件/命令逐个调用验证输出与 ps1 版行为一致（截断、错误格式 `ERROR:`）；pytest 通过。
**Depends:** 1

### Task 4: LLM SSE 流式客户端
**What:** `stream_chat`（urllib 逐行 SSE、reasoning_content、tool_calls 增量拼接）。
**Files:** `oksir/llm.py`
**Acceptance:** 冒烟：真实 DeepSeek 调用，控制台打印流式 delta 与 tool_calls 拼装结果。
**Depends:** 2

### Task 5: events + agent 主循环
**What:** Sink 协议、ConsoleSink；Agent 循环（≤25 轮工具循环、事件发射、消息列表管理）。
**Files:** `oksir/events.py`, `oksir/agent.py`
**Acceptance:** FakeLLM 驱动一轮"调用工具→回填→收尾"的循环验证；`python -m oksir "你好"` 控制台单发真实 API 可用。
**Depends:** 3, 4

### Task 6: Web server（原功能全量）
**What:** ThreadingHTTPServer + 全部旧端点 + 静态文件；`/chat` NDJSON（WebSink 加锁）。
**Files:** `oksir/server.py`
**Acceptance:** 冒烟：起服务，curl `/chat` 流式输出、会话增删改查端点可用。
**Depends:** 5

### Task 7: Web UI 移植（原功能全量）
**What:** 三文件拆分移植：侧栏会话、流式渲染、reasoning、工具块、配置弹窗、文件浏览、智能滚动。
**Files:** `web/{index.html,app.js,style.css}`
**Acceptance:** 浏览器实测：发消息流式渲染、会话切换/重命名/删除、配置弹窗、智能滚动。
**Depends:** 6

### Task 8: TriLayer 编排（spawn / 契约 / 并行）
**What:** TaskSpec、三层 prompt、spawn 工具（L1→L2→L3）、严格纪律 prompt、JSON 契约校验重试、多 spawn 并行线程、每回合 ≤8 上限、L3 白名单 + 无 spawn。
**Files:** `oksir/trilayer.py`, `oksir/agent.py`（spawn 工具接线）, `tests/test_trilayer.py`
**Acceptance:** FakeLLM 测试：L1 spawn L2 → L2 spawn L3 → 契约回传链路；白名单越权报错；JSON 格式不符触发重试；并行 spawn 汇总顺序正确；pytest 通过。真实冒烟一次。
**Depends:** 5

### Task 9: 浮窗 + 子 agent 模态框
**What:** `agent_spawn/agent_status/agent_event` 三事件 UI；右上角圆形浮窗（层级着色、呼吸/✓/✗）、点击模态框（TaskSpec + 实时进度 + 最终回复）；刷新后从会话重建终态。
**Files:** `web/app.js`, `web/style.css`, `web/index.html`
**Acceptance:** 浏览器实测：触发一个会 spawn 的任务，浮窗出现→状态流转→模态框实时滚动进度→完成态；刷新浮窗仍在（终态）。
**Depends:** 7, 8

### Task 10: ask_user 工具 + 问题卡片
**What:** ask 工具（L1 only、PendingAsk 注册、Event 阻塞、300s 超时）、`POST /answer`、UI 问题卡片（选项/输入/提交/已答态）。
**Files:** `oksir/tools/ask.py`, `oksir/server.py`, `web/{app.js,index.html,style.css}`, `oksir/agent.py`
**Acceptance:** 浏览器实测：L1 发起提问→卡片渲染→点选项→回合继续且 tool result 为 `USER: ...`；L2 无法调用（工具不在表）。
**Depends:** 8, 9

### Task 11: 收尾
**What:** ruff 全绿、README 增补 Python 版说明、全链路真实冒烟（三层 + ask）、整理提交历史。
**Files:** `README.md`, `docs/*`
**Acceptance:** `scripts/check.ps1` 全绿；一条真实消息走完 L1→L2→L3 + ask 流程；全部 commit 干净。
**Depends:** 10

## Execution Strategy

- 串行为主（1→11，依赖链硬）；Task 3 与 4 可并行（互不依赖），Task 7 的 UI 移植可与 Task 8 并行（契约已定）。
- Checkpoints：Task 7 后（原功能全量可用的可运行版本）与 Task 10 后（全部功能）各做一次完整冒烟。
- Git：每 Task 一个或多个本地 commit，message 风格沿用仓库现有英文祈使句；永不 push。

## Global Constraints

- 仅 Python 标准库；Python 3.13。
- 行为对齐 `agent.ps1`：工具输出截断 8000/20000 字符、`ERROR:` 前缀、25 轮上限、bash 120s 超时、会话 schema 不变。
- 新代码必须过 ruff（check + format）；不修改 `agent.ps1`。
- 事件/工具/端点契约以 `docs/spec.md` 为准，实现偏离需先改 spec。
