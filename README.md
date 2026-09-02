# YESIR

> AIOS 构思的第一块实体：TriLayer Multiagent + Inquire 主动发问 + MCP 生态接入。
> 名字来自它的工作方式：下层 agent 对上层交差时说 "OK, sir"，需要人拍板时主动 Inquire。

> 一个 AIOS 的幽灵，已经悄悄潜伏在主机里——打磨，不断地打磨，直到有一天。

## 出发点：AIOS

YESIR 的出发点不是"再写一个 coding agent"，而是一套 AIOS（AI Operating System）
构思的第一步落地。那套构思的几条核心判断：

- AIOS 不该是"长按电源键激活"的东西，而应是**无时无处不在的伙伴**；
- 它不替代当下的 OS，而是重要的补充——**Let everyone accessible**；
- 未来的 AIOS 需要 **MCP 生态**（或类似技术）的支撑；
- **Multiagent** 不是 harness 的子范式，而是 AIOS 的核心范式之一；
- Agent 的**主动发问机制**（需要人拍板时主动 Inquire）必须被认真对待。

YESIR 把其中三条直接做成了架构支柱：

| 日记里的判断 | YESIR 中的实体 |
|---|---|
| Multiagent 是 AIOS 的核心范式 | **TriLayer** 分层编排 |
| Agent 需要主动发问机制 | **Inquire**（`ask_user` 问题卡片） |
| AIOS 需要 MCP 生态 | **内置 MCP 客户端**（stdio） |

工程血缘上，它由 [Psi](../Psi)（PowerShell 单文件 harness）重生而来：Psi 证明了
harness 的核心可以小到几百行；YESIR 换用 Python，把重点放在多层级编排、人机
问答与工具生态上。

## 核心

- **TriLayer**：L1 Orchestrator（唯一面向用户）→ L2 Task Agent → L3 Worker（工具受限的基础工人）。
  上层派发时写下 `TaskSpec{goal, reply_format}`，下层严格按契约执行、按格式交差。
- **Inquire**：L1 通过 `ask_user` 工具主动向用户发问——选项卡片 + 自由输入，答案直接回到 agent 回合中。
- **MCP 客户端**：内置 Model Context Protocol（stdio 传输）客户端，`config.json` 配置即可把任意 MCP server 的工具挂进 agent。
- **失败重试**：回合失败（余额不足、断网等，报错原文全量显示）后 `Alt+R` 不加提示词、从原上下文继续。
- **零依赖**：纯 Python 标准库；Web UI 仅从 CDN 加载 marked.js。

## 快速开始

```powershell
# 配置 config.json（endpoint / api_key / model），或设置 OPENAI_* 环境变量
python -m yesir            # 用法帮助
python -m yesir "问题"     # 终端单次问答
python -m yesir --web      # 浏览器 UI
```

## MCP

`config.json` 中配置 stdio MCP server，重启后其工具自动注入 L1/L2（L3 基础工人不持有）：

```json
"mcp_servers": {
  "fs": {
    "command": "node",
    "args": ["node_modules/@modelcontextprotocol/server-filesystem/dist/index.js",
             "C:/allow/dir"]
  }
}
```

- 工具以 `mcp__<server>__<tool>` 命名注入，启动横幅列出已加载的清单；
  某个 server 起不来只跳过它，不影响回合。
- Windows 上建议用 `node <dist>/index.js` 直启而非 `npx`：子进程无法直接
  exec `.cmd` 包装器，且免去 npx 联网。
- 协议：JSON-RPC 2.0 over stdio，2025-06-18 `initialize` 握手；请求超时自动
  发 `notifications/cancelled`；server 进程意外退出后下次调用自动重连。

## Web UI

- 会话侧栏：过滤、重命名、删除（自定义确认模态框）。
- 回合失败后状态栏提示 `Alt+R` 重试；`Esc` 中断当前回合。
- LLM 报错（含 HTTP 状态码与响应体原文）直接渲染在聊天流中。

## Inquire（ask_user）

仅 L1 Orchestrator 持有 `ask_user` 工具。当它需要用户拍板时：

1. L1 调用 `ask_user {question, options?, allow_custom?}` → 回合挂起；
2. Web UI 在聊天流中渲染问题卡片（选项按钮 + 可选自由输入）；
3. 用户点选或输入 → `POST /answer {id, value}` 唤醒回合；
4. 工具返回 `USER: <答案>`，L1 带着答案继续干活。

用户 300 秒未回答则返回 `ERROR: 用户未回答`，L1 自行决定后续。终端模式下
问题只打印不等待作答渠道，同样会在超时后继续。

## 开发

```powershell
scripts\check.ps1          # ruff lint + format + pytest 一键门禁
```

设计 / 规格 / 计划见 `docs/`。
