# Coding agent 对比评测

## 选型

| 评测 | 主要任务 | 本项目用途 |
| --- | --- | --- |
| [SWE-bench Verified](https://www.swebench.com/) | 真实 GitHub issue 修复 | 常用参照，但高分段区分度有限 |
| [SWE-bench Pro](https://scaleapi.github.io/SWE-bench_Pro-os/) | 更长的软件工程任务 | 后续扩展，运行成本较高 |
| [Terminal-Bench 2.0](https://www.tbench.ai/) | 容器化终端任务，测试脚本评分 | 当前三方对比的共同任务集 |

这里选择 [Harbor](https://docs.harborframework.com/core-concepts/jobs/run-a-job) 官方 harness 运行 Terminal-Bench 2.0。Harbor 已内置 [Claude Code 和 Codex](https://docs.harborframework.com/core-concepts/agents/pre-integrated-agents)；`benchmarks/harbor_teddycode_agent.py` 将当前 TeddyCode checkout 打包上传到每个任务容器，三者分别运行在相同数据集的新容器中，由同一任务 verifier 评分。

## 准备

需要 Linux Docker 容器可用、Python 3.12+ 的 Harbor 主机环境和三方模型凭据。按照 [Harbor 安装说明](https://docs.harborframework.com/getting-started/installation) 安装 `harbor`，并确认 `harbor --version`、`docker info` 可用。将 `OPENAI_API_KEY` 和 `ANTHROPIC_API_KEY` 放在主机环境变量中；TeddyCode 使用 DeepSeek 时另设 `DEEPSEEK_API_KEY`。Claude Code 和 Codex 的凭据转发由 Harbor 内置适配器处理，TeddyCode 适配器只向 agent 执行阶段传递对应环境变量。

从仓库根目录执行：

```bash
python scripts/run_coding_agent_comparison.py \
  --teddycode-model deepseek/deepseek-chat \
  --claude-model anthropic/claude-sonnet-4-6 \
  --codex-model openai/gpt-5.4 \
  --task-limit 3
```

上述模型 ID 是命令示例，实际运行前应改为你的账户可用的精确模型 ID。先用 `--dry-run` 检查三条命令。`--task-limit 0` 跑完整数据集；`--attempts 3` 做重复试验。默认串行、每个 agent 一次尝试，降低本机资源争用。通过 `--dataset` 可切换到 Harbor 支持的其他公开数据集；三者必须保持相同值。任务限制使用同一排序的前 N 个任务，正式报告建议完整数据集或显式固定任务筛选。

结果位于 `artifacts/harbor-jobs/`，运行清单记录数据集、模型、任务数、尝试数、并发和各 job 状态。用 `harbor view artifacts/harbor-jobs` 查看各 job 的 reward、任务轨迹、耗时和成本。对比时报告 **resolved/reward、完成任务数、失败/超时数、模型版本、CLI 版本、Harbor 版本、任务集版本、尝试次数与硬件环境**。安装失败和基础设施失败应单列，不能当作能力失败；不应把不同模型的结果称为纯粹的 agent harness 差异。

## 范围与限制

- 当前接入是可运行的评测入口，仓库没有预填任何三方分数；需要实际凭据、Docker 和 benchmark 数据下载。
- TeddyCode 适配器在每次 task 中安装当前 checkout 的 Python 源码，避免只测到 PyPI 旧版本；不打包本地 `.env`、配置文件或测试文件。
- 当前 TeddyCode 的非交互运行限制为 100 steps，Claude Code 与 Codex 使用 Harbor 默认 agent 参数。若正式发表结果，应进一步对齐超时、预算、网络、权限和 prompt 模板，并保留 Harbor job 配置与每题轨迹。
- Terminal-Bench 主要测终端任务。仓库级 issue 修复还需要在 SWE-bench 系列上复测。
