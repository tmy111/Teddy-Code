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

Pico 启动时会读取项目根目录的 `.env`。本地真实 key 放在 `.env`，仓库只保留 `.env.example`。配置优先级是：

```text
显式 CLI 参数 > .env 里的 PICO_* 变量 > 旧环境变量 > 代码默认值
```

本地第一次配置：

```bash
cp .env.example .env
```

然后把要使用的 provider key 填进去。`.env` 已经被 `.gitignore` 忽略，不要提交真实 key。

### OpenAI 兼容接口

默认 OpenAI 兼容接口使用 right.codes 的 Codex endpoint：

```bash
PICO_OPENAI_API_BASE="https://www.right.codes/codex/v1"
PICO_OPENAI_API_KEY="your-api-key"
PICO_OPENAI_MODEL="gpt-5.4"
```

也可以改成其他 OpenAI-compatible 服务：

```bash
PICO_OPENAI_API_BASE="https://your-api.example/v1"
PICO_OPENAI_API_KEY="your-api-key"
PICO_OPENAI_MODEL="gpt-5.4"
```

```bash
uv run pico --provider openai
```

### Anthropic 兼容接口

默认 Anthropic 兼容接口使用 right.codes 的 Claude endpoint：

```bash
PICO_ANTHROPIC_API_BASE="https://www.right.codes/claude/v1"
PICO_ANTHROPIC_API_KEY="your-api-key"
PICO_ANTHROPIC_MODEL="claude-sonnet-4-6"
```

```bash
uv run pico --provider anthropic
```

如果你的服务端对多个兼容接口复用了同一套密钥，`pico` 也支持从 `PICO_ANTHROPIC_API_KEY` 回退到 `ANTHROPIC_API_KEY`、`PICO_RIGHT_CODES_API_KEY`、`RIGHT_CODES_API_KEY`、`PICO_OPENAI_API_KEY` 或 `OPENAI_API_KEY`。

### DeepSeek

```bash
PICO_DEEPSEEK_API_KEY="your-api-key"
PICO_DEEPSEEK_MODEL="deepseek-v4-pro"
```

```bash
uv run pico --provider deepseek
```

默认 DeepSeek base URL 是 `https://api.deepseek.com/anthropic`，走 DeepSeek 的 Anthropic 兼容接口。如果需要改到代理服务，可以设置 `PICO_DEEPSEEK_API_BASE` 或启动时传 `--base-url`。

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
