# YESIR

> TriLayer Agent + Inquire 机制的 Python coding agent harness。
> 名字来自它的工作方式：下层 agent 对上层交差时说 "OK, sir"，需要人拍板时主动 Inquire。

由 [Psi](../Psi)（PowerShell 单文件 harness）重生而来：Psi 证明了 harness 的核心可以小到几百行；
YESIR 换用 Python 并把重点放在**多层级 agent 编排**与**人机问答机制**上。

## 核心

- **TriLayer**：L1 Orchestrator（唯一面向用户）→ L2 Task Agent → L3 Worker（工具受限的基础工人）。
  上层派发时写下 `TaskSpec{goal, reply_format}`，下层严格按契约执行、按格式交差。
- **Inquire**：L1 通过 `ask_user` 工具主动向用户发问——选项卡片 + 自由输入，答案直接回到 agent 回合中。
- **零依赖**：纯 Python 标准库；Web UI 仅从 CDN 加载 marked.js。
- **对接任何 OpenAI 兼容 API**。

## 快速开始

```powershell
# 配置 config.json（endpoint / api_key / model），或设置 OPENAI_* 环境变量
python -m yesir            # 用法帮助
python -m yesir "问题"     # 终端单次问答
python -m yesir --web      # 浏览器 UI
```

## 开发

```powershell
scripts\check.ps1          # ruff lint + format + pytest 一键门禁
```

## Inquire（ask_user）

仅 L1 Orchestrator 持有 `ask_user` 工具。当它需要用户拍板时：

1. L1 调用 `ask_user {question, options?, allow_custom?}` → 回合挂起；
2. Web UI 在聊天流中渲染问题卡片（选项按钮 + 可选自由输入）；
3. 用户点选或输入 → `POST /answer {id, value}` 唤醒回合；
4. 工具返回 `USER: <答案>`，L1 带着答案继续干活。

用户 300 秒未回答则返回 `ERROR: 用户未回答`，L1 自行决定后续。终端模式下
问题只打印不等待作答渠道，同样会在超时后继续。

设计 / 规格 / 计划见 `docs/`。
