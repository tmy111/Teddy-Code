from pathlib import Path


def test_core_modules_stay_below_entropy_budget():
    root = Path(__file__).resolve().parents[1]
    budgets = {
        "pico/core/runtime.py": 950,
        "pico/core/runtime_events.py": 90,
        "pico/core/runtime_consumers.py": 90,
        "pico/core/artifacts.py": 130,
        "pico/core/task_state.py": 140,
        "pico/core/context_manager.py": 420,
        "pico/core/context_usage.py": 120,
        "pico/core/compact.py": 180,
        "pico/core/engine.py": 450,
        "pico/core/permissions.py": 140,
        "pico/core/tool_policy.py": 90,
        "pico/core/plan_mode.py": 140,
        "pico/core/tool_executor.py": 180,
        "pico/core/tool_profiles.py": 80,
        "pico/core/turn_history.py": 250,
        "pico/tools/registry.py": 360,
    }

    for relative_path, max_lines in budgets.items():
        line_count = len((root / relative_path).read_text(encoding="utf-8").splitlines())
        assert line_count <= max_lines, f"{relative_path} has {line_count} lines, budget is {max_lines}"
