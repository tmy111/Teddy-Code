"""Architecture budget tests for runtime module boundaries."""

from pathlib import Path


def test_core_modules_stay_below_entropy_budget():
    root = Path(__file__).resolve().parents[1]
    budgets = {
        "teddycode/core/runtime.py": 950,
        "teddycode/core/before_final_hooks.py": 140,
        "teddycode/core/evidence_summaries.py": 90,
        "teddycode/core/final_readiness.py": 120,
        "teddycode/core/final_readiness_artifacts.py": 160,
        "teddycode/core/final_readiness_context.py": 60,
        "teddycode/core/final_readiness_reasons.py": 60,
        "teddycode/core/final_readiness_tools.py": 100,
        "teddycode/core/governance.py": 80,
        "teddycode/core/runtime_events.py": 90,
        "teddycode/core/runtime_consumers.py": 90,
        "teddycode/core/artifacts.py": 130,
        "teddycode/core/task_state.py": 140,
        "teddycode/core/todo_ledger.py": 120,
        "teddycode/core/worker_manager.py": 220,
        "teddycode/core/context_manager.py": 420,
        "teddycode/core/context_budget_summary.py": 130,
        "teddycode/core/context_handoff.py": 240,
        "teddycode/core/context_orchestrator.py": 210,
        "teddycode/core/context_pressure.py": 140,
        "teddycode/core/context_report.py": 140,
        "teddycode/core/context_retention.py": 90,
        "teddycode/core/context_replacements.py": 160,
        "teddycode/core/context_sections.py": 170,
        "teddycode/core/context_usage.py": 130,
        "teddycode/core/compact.py": 250,
        "teddycode/core/compact_summary.py": 130,
        "teddycode/core/completion_governance.py": 240,
        "teddycode/core/engine.py": 470,
        "teddycode/core/model_errors.py": 100,
        "teddycode/core/model_router.py": 40,
        "teddycode/core/permissions.py": 140,
        "teddycode/core/tool_policy.py": 90,
        "teddycode/core/plan_mode.py": 140,
        "teddycode/core/tool_executor.py": 181,
        "teddycode/core/tool_profiles.py": 80,
        "teddycode/core/tool_result_artifacts.py": 60,
        "teddycode/core/turn_transitions.py": 90,
        "teddycode/core/verification.py": 80,
        "teddycode/core/turn_history.py": 280,
        "teddycode/core/media_history.py": 20,
        "teddycode/features/skills.py": 220,
        "teddycode/features/skills_bundled.py": 120,
        "teddycode/features/skills_runtime.py": 140,
        "teddycode/tools/registry.py": 360,
        "teddycode/tools/todos.py": 80,
        "teddycode/tools/agents.py": 90,
    }

    for relative_path, max_lines in budgets.items():
        line_count = len((root / relative_path).read_text(encoding="utf-8").splitlines())
        assert line_count <= max_lines, f"{relative_path} has {line_count} lines, budget is {max_lines}"
