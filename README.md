# pico

`pico` 是一个面向代码仓库的轻量本地 coding agent。它直接跑在终端里，先看当前工作区，再用一组受约束的工具去读文件、改文件、跑命令，并把会话状态保存在本地 `.pico/` 目录里。

它更像一个能在仓库里持续工作的命令行助手，不是纯聊天窗口。你可以拿它做代码排查、测试修复、仓库分析，或者让它在当前项目里执行一次性的工程任务。

## 适合做什么

- 在本地仓库里排查测试失败
- 读取当前代码结构并给出修改建议
- 基于现有文件做小步迭代，而不是脱离仓库空想
- 在会话中保留上下文，支持继续上一次工作

## 主要特性

- 包名是 `pico`
- CLI 命令是 `pico`
- 模块入口是 `python -m pico`
- 会话保存在 `.pico/sessions/`
- 每次运行的工件保存在 `.pico/runs/<run_id>/`
- 支持三类模型后端：
  - OpenAI 兼容 Responses API
  - Anthropic 兼容 Messages API
  - DeepSeek Anthropic 兼容 API

## 使用截图

CLI 帮助信息：

![pico help](assets/screenshots/pico-help.png)

启动界面：

![pico start](assets/screenshots/pico-start.png)

REPL 内置命令与会话路径：

![pico repl](assets/screenshots/pico-repl.png)

## 安装

需要 Python 3.10+。

如果你用 `uv`，直接安装依赖：

```bash
uv sync
```

如果你已经在自己的 Python 环境里工作，也可以直接装成可编辑模式：

```bash
pip install -e .
```

## 快速开始

在当前仓库里启动交互模式。当前推荐使用 DeepSeek：

```bash
uv run pico --provider deepseek
```

指定另一个工作目录：

```bash
uv run pico --cwd /path/to/repo
```

直接跑一次性任务：

```bash
uv run pico --provider deepseek "inspect the test failures and propose a fix"
```

如果当前环境已经安装过包，也可以直接这样启动：

```bash
python -m pico --provider deepseek
```

## 模型后端

Pico 的 provider 配置是 TOML profile。用户选择的是 `deepseek`、`openai` 这类 profile；runtime 真正分派的是 profile 里的 `protocol`，目前支持 `openai` 和 `anthropic` 两种协议。

配置文件加载顺序是：

1. `~/.config/pico/config.toml`
2. 当前项目向上查找的 `.pico.toml`

后加载的项目配置会覆盖全局配置。也可以用 `--config /path/to/config.toml` 指定单个配置文件。

配置优先级是：

```text
显式 CLI 参数 > shell 环境变量 > TOML profile > 旧 .env 兼容变量 > 代码默认值
```

本地第一次配置：

```bash
cp .pico.toml.example .pico.toml
```

然后把要使用的 provider key 填进去。`.pico.toml` 已经被 `.gitignore` 忽略，不要提交真实 key。

### 配置示例

```toml
provider = "deepseek"

[providers.deepseek]
protocol = "anthropic"
api_key = "your-api-key"
base_url = "https://api.deepseek.com/anthropic"
model = "deepseek-v4-pro"

[providers.openai]
protocol = "openai"
api_key = "your-api-key"
base_url = "https://www.right.codes/codex/v1"
model = "gpt-5.4"
```

```bash
uv run pico
uv run pico --provider openai
uv run pico --provider deepseek --model deepseek-v4-pro
```

### OpenAI 兼容接口

默认 OpenAI 兼容接口使用 right.codes 的 Codex endpoint：

```toml
[providers.openai]
protocol = "openai"
api_key = "your-api-key"
base_url = "https://www.right.codes/codex/v1"
model = "gpt-5.4"
```

```bash
uv run pico --provider openai
```

### Anthropic 兼容接口

默认 Anthropic 兼容接口使用 right.codes 的 Claude endpoint：

```toml
[providers.anthropic]
protocol = "anthropic"
api_key = "your-api-key"
base_url = "https://www.right.codes/claude/v1"
model = "claude-sonnet-4-6"
```

```bash
uv run pico --provider anthropic
```

### DeepSeek

DeepSeek 是一个 profile，底层协议是 Anthropic-compatible：

```toml
[providers.deepseek]
protocol = "anthropic"
api_key = "your-api-key"
base_url = "https://api.deepseek.com/anthropic"
model = "deepseek-v4-pro"
```

```bash
uv run pico --provider deepseek
```

如果需要临时改到代理服务，可以启动时传 `--base-url`，或者在 profile 里改 `base_url`。

### 环境变量

环境变量用于临时覆盖 TOML：

- `PICO_PROVIDER` / `PICO_API_KEY` / `PICO_BASE_URL` / `PICO_MODEL`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL`
- `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`

旧的 `.env` + `PICO_OPENAI_*`、`PICO_ANTHROPIC_*`、`PICO_DEEPSEEK_*` 仍然能用，但只作为兼容兜底。

## 常用交互命令

- `/help`：查看内置命令
- `/memory`：查看提炼后的工作记忆
- `/skills`：查看可用技能和 slash workflow
- `/review`、`/test`、`/commit`、`/simplify`：调用内置技能
- `/session`：查看当前会话文件路径
- `/context`：查看当前 prompt 的上下文用量
- `/compact`：手动压缩较旧的会话历史
- `/reset`：清空当前会话状态
- `/exit` 或 `/quit`：退出 REPL

## Skills

`pico` 会加载三类技能，后面的同名技能覆盖前面的：

- 内置技能：`review`、`test`、`commit`、`simplify`
- 用户技能：`~/.pico/skills/<name>/SKILL.md`
- 项目技能：`skills/<name>/SKILL.md` 或 `.pico/skills/<name>/SKILL.md`

技能文件可以带一段简单 frontmatter：

```markdown
---
name: deploy
description: Deploy checklist
argument-hint: target
context: inline
allowed-tools: read_file, search
paths: src/*.py, tests/*.py
---
Check deployment readiness for $ARGUMENTS from ${PICO_SKILL_DIR}.
```

在 REPL 或 one-shot 模式里输入 `/deploy staging` 时，技能内容会被展开成一次普通 session 请求，因此仍然走同一套工具、审批、事件和验证链路。`context: fork` 会用隔离 session 执行，不污染主会话历史；`disable-model-invocation: true` 会只渲染 prompt，不发起模型调用。

支持的 metadata：

- `name` / `description` / `when-to-use`
- `arguments` 或 `argument-hint`
- `context: inline|fork`
- `allowed-tools: read_file, search`
- `disable-model-invocation: true|false`
- `model`
- `paths`
- `user-invocable: true|false`

## Task Ledger

`pico` 提供 session 级任务账本，供模型把较大的工作拆成可追踪 todo。账本保存在 session JSON 里，每次变更都会写入 `.pico/sessions/<session>.events.jsonl`，并进入本轮 `report.json`。

模型可使用这些工具：

- `todo_add(content, status='pending', priority='normal', note='')`
- `todo_update(todo_id, status?, content?, priority?, note?)`
- `todo_list()`

支持的状态是 `pending`、`in_progress`、`done`、`blocked`；优先级是 `low`、`normal`、`high`。Plan mode 下也可以使用 todo 工具，用来保持计划和执行账本同步。

## Subagents

`pico` 提供 session 级 worker manager。主 agent 可以通过工具启动一个子 agent、继续同一个子 agent，或者停止它：

- `agent(description, prompt, subagent_type='worker', write_scope=[])`
- `send_message(to, message)`
- `task_stop(task_id)`

支持两种子 agent：

- `Explore`：只读，用于快速搜索和理解代码。Plan mode 下只允许启动 `Explore`。
- `worker`：可以执行多步任务，但写文件必须落在 `write_scope` 指定的路径内，且不会再暴露子 agent 工具。

子 agent 完成后会把 `<task-notification>` 写回主 session history，并在 `.pico/sessions/<session>.events.jsonl` 里记录 `worker_started` / `worker_finished`。本轮 `report.json` 也会包含 `workers` 快照，便于复盘真实 session。

## 安全与持久化

`pico` 不会默认把所有动作都放开。像 shell 执行、文件写入这类高风险操作，会受审批模式控制：

- `--approval ask`
- `--approval auto`
- `--approval never`

每次运行结束后，都会在 `.pico/runs/<run_id>/` 下写出这些文件：

- `task_state.json`
- `trace.jsonl`
- `report.json`

这些内容默认只保存在本地，不需要跟仓库一起提交。

## 开发

如果装了 Ruff，可以这样检查：

```bash
uv run ruff check .
```
