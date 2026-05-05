# Pico Tool Policy Layer

Gate 4 把工具治理拆成两层：

- Permission layer 回答“有没有权调用这个工具”。
- Tool policy layer 回答“当前上下文下这样用工具是否合理”。

这不是第二套权限系统。`PermissionChecker` 仍然负责 plan mode、read-only mode 和 approval policy。`ToolPolicyChecker` 只在权限允许后运行，拒绝那些会让 agent 产生脏上下文或不可复盘修改的工具用法。

## First Rules

第一版只落四条规则：

- `patch_file` 必须先 `read_file` 目标文件，并且 read 后的 freshness 仍然匹配当前文件。
- `write_file` 创建新文件可以直接执行；覆盖已有文件必须先 `read_file`。
- `run_shell` 不用于普通仓库检索；明显的 `cat`、`grep`、`rg`、`find`、`ls` 这类命令会被要求改用 `read_file`、`search` 或 `list_files`。
- 长 `run_shell` 输出写入 `.pico/runs/<run>/artifacts/`，history/trace 里只保留 clipped result 和 artifact path。

## Data Flow

```text
tool_executor.run_tool()
  -> validate_tool()
  -> PermissionChecker
  -> ToolPolicyChecker
  -> execute tool
  -> memory / trace / evidence
```

Policy 拒绝会写入 `_last_tool_result_metadata`，并通过 `tool_policy_decision` 进入 session event log。真实执行后的长输出 artifact 会进入 trace/report 的 evidence path，不把大文本塞回上下文。

## Why This Matters

Coding agent 的风险不只来自“能不能写文件”，还来自“在没读过文件时凭空 patch”和“用 shell 做所有事情”。这层 policy 让 Pico 能在面试里解释工具协议：模型不是拿到一串白名单就随便用，而是必须遵守读、改、验收、复盘的运行约束。
