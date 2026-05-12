<div align="center">

# pico

**轻量、本地、有记忆的终端 coding agent**

跑在终端里 · 看得见每一步 · 跨 session 记住你

</div>

---

### **亮点：分层记忆 + auto-dream 跨 session 整合**

> 大部分 coding agent 重启一次就忘干净。pico 把每次会话的关键信号沉淀到本地 `.pico/memory/`，后台 auto-dream 会把它们整理成长期可检索的 topic 文件。下一次启动 pico，它认得这个仓库。

![pico repl](assets/screenshots/pico-repl.png)

[完整记忆系统文档 →](docs/memory.md)

---

## 特性

### 核心

- **交互式 REPL** — 流式输出、内置命令补全、`/resume` 续接历史会话
- **8 个内置工具** — `list_files` `read_file` `search` `run_shell` `write_file` `patch_file` `ask_user` `agent`
- **Plan mode** — 计划阶段读代码、起 explore 子 agent，写操作隔离到执行阶段
- **审批模式** — `ask` / `auto` / `never`，写操作和 shell 默认要确认
- **会话持久化** — 自动保存对话，事件流写入 `.pico/sessions/`
- **上下文预算** — 60K 字符按 prefix/memory/skills/relevant_memory/history 切，超额自动压缩
- **三种 provider 协议** — Anthropic Messages API / OpenAI Responses API / DeepSeek

### 进阶

| 特性 | 说明 | 文档 |
|------|------|------|
| **分层记忆** | working memory + daily logs + durable topics + auto-dream | [docs →](docs/memory.md) |
| **Auto-dream** | 后台触发，把零散日志整合成 4 类 durable topic | [docs →](docs/memory.md) |
| **Skills** | `/review` `/test` `/commit` `/simplify` 等 slash workflow | [docs →](docs/skills.md) |
| **Sandbox** | bubblewrap 隔离 `run_shell` | [docs →](docs/sandbox.md) |
| **Workspace fingerprint** | 工作区指纹 + prompt cache 友好的 prefix 复用 | — |
| **Runs/ 审计** | 每次运行写 `task_state.json` + `trace.jsonl` + `report.json` | — |

---

## 快速开始

### 前置

- Python 3.10+
- 三种 provider 任选一个 API key：[Anthropic](https://console.anthropic.com/) / OpenAI 兼容 / [DeepSeek](https://platform.deepseek.com)

### 安装

```bash
# 一键安装（推荐）
curl -fsSL https://raw.githubusercontent.com/martin-los/pico/main/install.sh | bash

# 或手动
git clone https://github.com/martin-los/pico.git
cd pico
pip install -e .
```

### 配置 API key

最简单的方式是环境变量：

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # 使用 Claude
export OPENAI_API_KEY=sk-...             # 使用 GPT
export DEEPSEEK_API_KEY=sk-...           # 使用 DeepSeek
```

或者在项目根写一个 `.pico.toml`：

```toml
provider = "deepseek"

[providers.deepseek]
protocol = "anthropic"
api_key = "sk-..."
base_url = "https://api.deepseek.com/anthropic"
model = "deepseek-v4-pro"

[providers.anthropic]
protocol = "anthropic"
api_key = "sk-ant-..."
base_url = "https://api.anthropic.com"
model = "claude-sonnet-4-6"
```

完整配置参考 [docs/configuration.md](docs/configuration.md)。

### 运行

```bash
pico                                      # 交互式 REPL
pico "找出测试失败的根因并提议修复"        # 一次性任务
pico --provider deepseek                  # 切换 provider
pico --resume latest                      # 续接上一个 session
pico --approval auto                      # 跳过写操作审批
pico --cwd /path/to/repo                  # 切换工作目录
```

### 第一次会话

```text
$ pico
+============================================+
|        /\___/\\                            |
|       (  o o  )    pico                    |
|       /   ^   \\   local coding agent      |
|      /|       |\\  calm shell, ready       |
+============================================+
| WORKSPACE  /you/project                    |
| MODEL      claude-sonnet-4-6               |
| APPROVAL   ask    SESSION  20260513-...    |
+============================================+

> 列出仓库根目录下的 Python 包
↳ list_files(.) ✓
找到 3 个包: src/, tests/, scripts/

> 读 src/__init__.py 然后告诉我导出哪些符号
↳ read_file(src/__init__.py) ✓
导出 4 个：Agent, Workspace, Session, run_agent。

> /remember 这个项目用 Anthropic API，密钥从 .env 加载
Saved to daily log.

> /dream
Consolidation complete. 写入 topics/user-preferences.md 与 MEMORY.md。

> /exit
```

下次重新打开 pico 时，`MEMORY.md` 里已经有这条偏好；模型在新 session 中会主动用上。

---

## 工具

| 工具 | 用途 | 审批 |
|------|------|------|
| `list_files` | 列目录 | 自动通过 |
| `read_file` | 读文件按行区间 | 自动通过 |
| `search` | rg / fallback 搜索 | 自动通过 |
| `run_shell` | 执行 shell 命令 | 默认询问 |
| `write_file` | 写文件 | 默认询问 |
| `patch_file` | 精确字符串替换 | 默认询问 |
| `ask_user` | 反向问用户 | 自动通过 |
| `agent` | 起子 agent（Explore / worker） | 自动通过 |

Plan mode 多出 `enter_plan_mode` / `exit_plan_mode`；todo ledger 多出 `todo_add` / `todo_update` / `todo_list`。

---

## 数据路径

| 数据 | 位置 |
|------|------|
| 会话历史 | `.pico/sessions/<id>.json` |
| 事件流 | `.pico/sessions/<id>.events.jsonl` |
| 每次运行的工件 | `.pico/runs/<run_id>/` |
| 工作记忆 | session JSON 的 `memory` 字段 |
| 持久记忆 | `.pico/memory/` |
| 记忆索引 | `.pico/memory/MEMORY.md` |
| Daily logs | `.pico/memory/logs/YYYY/MM/YYYY-MM-DD.md` |
| Topic 文件 | `.pico/memory/topics/*.md` |
| 项目配置 | `.pico.toml` |
| 全局配置 | `~/.config/pico/config.toml` |
| 用户技能 | `~/.pico/skills/<name>/SKILL.md` |
| 项目技能 | `skills/<name>/SKILL.md` 或 `.pico/skills/<name>/SKILL.md` |

---

## 常用 slash 命令

| 命令 | 说明 |
|------|------|
| `/help` | 查看全部内置命令 |
| `/memory` | 显示 `MEMORY.md` 索引 |
| `/working-memory` | 显示当前 session 工作记忆 |
| `/remember <text>` | 追加一条记忆到今天的 daily log |
| `/dream` | 立即整合 daily log 到 topic 文件 |
| `/skills` | 列出可用技能 |
| `/review` `/test` `/commit` `/simplify` | 内置技能 |
| `/plan <topic>` | 进入 plan mode |
| `/plan-exit` | 退出 plan mode |
| `/resume <id\|latest>` | 续接历史 session |
| `/history` | 显示最近 session |
| `/session` | 显示当前 session 路径和状态 |
| `/context` | 显示上下文预算用量 |
| `/usage` | 显示 token / call 统计 |
| `/compact` | 手动压缩历史 |
| `/clear` | 清空当前 session 状态开新 session |
| `/exit` | 退出 |

---

## 项目结构

```
pico/
├── core/                  # 控制平面
│   ├── runtime.py         # Pico 主类（会话、记忆、prompt 装配）
│   ├── engine.py          # 单轮 turn 循环
│   ├── context_manager.py # prompt 预算切片 / 压缩
│   ├── tool_policy.py     # 工具策略（read-before-write 等）
│   ├── tool_profiles.py   # 工具组（default / dream / readonly / worker / plan）
│   ├── worker_manager.py  # 子 agent 生命周期
│   └── session_store.py   # 会话持久化
│
├── features/              # 可插拔特性
│   ├── memory.py          # 分层记忆 + auto-dream
│   ├── skills.py          # 技能加载
│   ├── skills_bundled.py  # 内置 /review /test /commit /simplify
│   └── sandbox/           # bubblewrap 隔离
│
├── tools/                 # 工具实现
│   ├── registry.py        # 工具注册
│   ├── agents.py          # agent / send_message / task_stop
│   ├── ask_user.py        # 反向问用户
│   ├── plan.py            # plan mode 工具
│   └── todos.py           # todo ledger
│
├── tui/                   # Textual TUI
├── providers/             # Anthropic / OpenAI 协议客户端
└── cli.py                 # CLI 入口
```

---

## 默认值

| 项 | 默认 | 说明 |
|----|------|------|
| `--max-steps` | 50 | 单轮最多模型 / 工具迭代次数 |
| `--max-new-tokens` | 按 provider 推断 | Anthropic 32000, OpenAI/DeepSeek 8192 |
| `--temperature` | 0.2 | 采样温度 |
| `--approval` | `ask` | 写操作默认询问 |
| `--sandbox` | `off` | 默认不沙盒，可设 `best_effort` 或 `required` |
| `--dream-interval` | 24（小时） | auto-dream 最小间隔 |
| `--dream-min-sessions` | 5 | auto-dream 触发所需最少新 session |

---

## 测试

```bash
pip install -e ".[dev]"
pytest tests/ -q                       # 单元测试
pytest tests/test_release_smoke.py     # release 烟测（需 API key）
```

---

## 文档

| 主题 | 链接 |
|------|------|
| 配置（API key / TOML / CLI flag） | [docs/configuration.md](docs/configuration.md) |
| 分层记忆 + auto-dream | [docs/memory.md](docs/memory.md) |
| Skills（自定义工作流） | [docs/skills.md](docs/skills.md) |
| Sandbox（命令隔离） | [docs/sandbox.md](docs/sandbox.md) |

---

## 许可证

MIT
