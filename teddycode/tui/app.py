from __future__ import annotations

"""TeddyCode 的 Textual 终端界面。

这个文件只负责界面层：展示消息、接收输入、处理快捷键和审批弹窗。
真正的 agent 构造、命令处理、模型/工具循环仍然复用 cli/core 里的逻辑。
"""

import asyncio
import threading
from functools import partial

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.events import Key

from ..cli import HELP_DETAILS, handle_repl_command
from .widgets import (
    AskUserPrompt,
    ChatLog,
    ConfirmPrompt,
    InputBar,
    StatusBar,
    ThinkingIndicator,
    ToolCard,
    WelcomeBanner,
    format_tool_args,
)


TEDDYCODE_TUI_CSS = """
Screen {
    layout: vertical;
    background: #0f1117;
}
"""


class TeddyCodeTuiApp(App):
    """包在 TeddyCode runtime 外面的一层 Textual shell。

    TUI 刻意保持为展示层：CLI 参数解析和 agent 构造仍在 teddycode.cli，
    每轮对话也复用普通 REPL 使用的 Engine.run_turn() 事件生成器。
    """

    CSS = TEDDYCODE_TUI_CSS
    BINDINGS = [
        Binding("enter", "submit_input", "Send", priority=True, show=False),
        Binding("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, agent, **kwargs) -> None:
        super().__init__(**kwargs)
        self.agent = agent
        # TUI 需要把 runtime 的阻塞式 approve/ask_user 回调桥接到界面弹窗。
        self._turn_count = 0
        self._running_tool_cards: list[ToolCard] = []
        self._confirm_prompt: ConfirmPrompt | None = None
        self._confirm_decision: tuple[threading.Event, dict] | None = None
        self._ask_user_prompt: AskUserPrompt | None = None
        self._ask_user_decision: tuple[threading.Event, dict] | None = None
        self._previous_approve = getattr(agent, "approve", None)
        self._previous_ask_user = getattr(agent, "ask_user_callback", None)
        self.agent.approve = self._approval_callback
        self.agent.ask_user_callback = self._ask_user_callback

    def compose(self) -> ComposeResult:
        """声明界面结构：欢迎区、聊天区、思考状态、状态栏和输入栏。"""

        yield WelcomeBanner(
            model_name=str(getattr(self.agent.model_client, "model", "")),
            cwd=str(getattr(self.agent, "root", "")),
            approval=str(getattr(self.agent, "approval_policy", "")),
        )
        yield ChatLog()
        yield ThinkingIndicator()
        yield StatusBar()
        yield InputBar()

    def on_mount(self) -> None:
        """界面挂载后初始化状态栏、聚焦输入框，并定期拉取 worker 通知。"""

        self.query_one(StatusBar).update_agent(self.agent)
        self.query_one(InputBar).focus_input()
        self.set_interval(0.5, self._drain_idle_worker_notifications)

    def on_unmount(self) -> None:
        """退出 TUI 时恢复 agent 原本的回调，避免污染外部 runtime。"""

        if self._previous_approve is not None:
            self.agent.approve = self._previous_approve
        self.agent.ask_user_callback = self._previous_ask_user

    def action_clear_screen(self) -> None:
        self.query_one(ChatLog).clear_messages()

    def action_submit_input(self) -> None:
        """Enter 键入口：优先处理弹窗，其次提交输入框里的用户消息。"""

        if self._ask_user_prompt is not None:
            self._resolve_ask_user(self._ask_user_prompt.selected_choice)
            return
        if self._confirm_prompt is not None:
            self._resolve_confirm(self._confirm_prompt.selected)
            return
        bar = self.query_one(InputBar)
        text = bar.input.value.strip()
        if not text or bar.input.disabled:
            return
        bar.history.append(text)
        bar.history_index = len(bar.history)
        bar.input.value = ""
        self._hide_welcome_banner()
        if text.startswith("/"):
            # 斜杠命令直接走 CLI 的 handle_repl_command，保持 TUI/REPL 行为一致。
            self.query_one(ChatLog).add_message("user", text)
            bar.hide_slash_suggestions()
            self._handle_command(text)
            return
        self.query_one(ChatLog).add_message("user", text)
        self._run_agent(text)

    def on_key(self, event: Key) -> None:
        """集中处理键盘交互，包括弹窗选择、slash 补全和历史输入切换。"""

        if self._ask_user_prompt is not None:
            if event.key in {"right", "down"}:
                self._ask_user_prompt.select_next()
                event.prevent_default()
            elif event.key in {"left", "up"}:
                self._ask_user_prompt.select_previous()
                event.prevent_default()
            elif event.key == "enter":
                self._resolve_ask_user(self._ask_user_prompt.selected_choice)
                event.prevent_default()
            elif event.key == "escape":
                self._resolve_ask_user("")
                event.prevent_default()
            return
        if self._confirm_prompt is not None:
            if event.key in {"y", "right"}:
                self._confirm_prompt.select_allow()
                event.prevent_default()
            elif event.key in {"n", "left"}:
                self._confirm_prompt.select_deny()
                event.prevent_default()
            elif event.key == "enter":
                self._resolve_confirm(self._confirm_prompt.selected)
                event.prevent_default()
            elif event.key == "escape":
                self._resolve_confirm(False)
                event.prevent_default()
            return
        bar = self.query_one(InputBar)
        if event.key == "tab" and bar.complete_slash_suggestion():
            event.prevent_default()
        elif event.key == "up" and bar.move_slash_selection(-1):
            event.prevent_default()
        elif event.key == "down" and bar.move_slash_selection(1):
            event.prevent_default()
        elif event.key == "escape":
            bar.hide_slash_suggestions()
            event.prevent_default()
        elif event.key == "up":
            bar.history_prev()
            event.prevent_default()
        elif event.key == "down":
            bar.history_next()
            event.prevent_default()

    def _handle_command(self, text: str) -> None:
        """处理 /help、/model、/history 等 REPL 命令。"""

        handled, should_exit, output = handle_repl_command(self.agent, text)
        if should_exit:
            self.exit()
            return
        if handled:
            self.query_one(ChatLog).add_message("assistant", output)
            self.query_one(StatusBar).update_agent(self.agent)
            return
        self.query_one(ChatLog).add_message(
            "assistant", f"Unknown command. Use /help.\n\n{HELP_DETAILS}"
        )

    def _run_agent(self, text: str) -> None:
        """启动一次后台 agent 运行，并让界面进入 busy/thinking 状态。"""

        self.query_one(InputBar).set_busy(True)
        self.query_one(ThinkingIndicator).show()
        self._thinking_timer = self.set_interval(
            0.15, self.query_one(ThinkingIndicator).advance
        )
        asyncio.create_task(self._agent_task(text))

    def _drain_idle_worker_notifications(self) -> None:
        if self.query_one(InputBar).input.disabled:
            return
        notifications = self.agent.engine.drain_worker_notifications()
        if not notifications:
            return
        chat = self.query_one(ChatLog)
        for notification in notifications:
            chat.add_message("assistant", f"[worker notification]\n{notification}")
        self.query_one(StatusBar).update_agent(self.agent)

    async def _agent_task(self, text: str) -> None:
        """把阻塞的 agent turn 放到线程池里跑，避免卡住 Textual 事件循环。"""

        loop = asyncio.get_running_loop()
        completed = False
        try:
            await loop.run_in_executor(None, partial(self._drive_turn, text))
            completed = True
        except Exception as exc:
            if self.is_running:
                try:
                    self.query_one(ChatLog).add_message("assistant", f"[Error] {exc}")
                except NoMatches:
                    pass
        finally:
            self._finish_agent_task(completed)

    def _drive_turn(self, text: str) -> None:
        """在线程池中驱动 Engine.run_turn()，再把事件投递回 UI 线程。"""

        for event in self.agent.engine.run_turn(text):
            try:
                self.call_from_thread(self._handle_runtime_event, dict(event))
            except RuntimeError:
                return

    def _handle_runtime_event(self, event: dict) -> None:
        """把 core Engine 事件翻译成界面更新。"""

        event_type = str(event.get("type", ""))
        if event_type == "model_requested":
            attempts = event.get("attempts", 0)
            tool_steps = event.get("tool_steps", 0)
            self.query_one(ThinkingIndicator).set_detail(
                f"model request {attempts}, tools {tool_steps}"
            )
            return
        if event_type == "model_parsed":
            kind = event.get("kind", "")
            self.query_one(ThinkingIndicator).set_detail(f"model returned {kind}")
            return
        if event_type == "tool_call":
            # 工具开始运行时先插入一张 running 状态的 ToolCard。
            name = str(event.get("name", ""))
            args = event.get("args") if isinstance(event.get("args"), dict) else {}
            self.query_one(ThinkingIndicator).set_detail(f"running {name}")
            card = self.query_one(ChatLog).add_tool_call(name, args)
            self._running_tool_cards.append(card)
            return
        if event_type == "tool_result":
            # 工具结束时根据 metadata 更新最近一张对应 ToolCard。
            self._finish_tool_card(event)
            self.query_one(ThinkingIndicator).set_detail("thinking after tool")
            return
        if event_type == "worker_notification":
            self.query_one(ChatLog).add_message(
                "assistant", f"[worker notification]\n{event.get('content', '')}"
            )
            return
        if event_type in {"retry", "runtime_notice", "final", "stop"}:
            self.query_one(ChatLog).add_message(
                "assistant", str(event.get("content", ""))
            )
            return

    def _finish_tool_card(self, event: dict) -> None:
        name = str(event.get("name", ""))
        card = None
        for candidate in reversed(self._running_tool_cards):
            if candidate.tool_name == name and candidate.status == "running":
                card = candidate
                break
        if card is None:
            card = self.query_one(ChatLog).add_tool_call(name, {})
        metadata = (
            event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        )
        content = str(event.get("content", ""))
        status = str(metadata.get("tool_status", "ok") or "ok")
        if status in {"error", "rejected", "partial_success"}:
            card.set_error(content)
        else:
            card.set_success(content)

    def _hide_welcome_banner(self) -> None:
        try:
            self.query_one(WelcomeBanner).add_class("hidden")
        except NoMatches:
            pass

    def _finish_agent_task(self, completed: bool) -> None:
        """一次 agent turn 结束后恢复输入框、停止动画并刷新状态栏。"""

        if not self.is_running:
            return
        try:
            self._stop_thinking()
            bar = self.query_one(InputBar)
            bar.set_busy(False)
            bar.focus_input()
            if completed:
                self._turn_count += 1
            status = self.query_one(StatusBar)
            status.update_turns(self._turn_count)
            status.update_agent(self.agent)
            usage = (getattr(self.agent, "last_prompt_metadata", {}) or {}).get(
                "context_usage"
            ) or {}
            status.update_context_usage(usage)
        except NoMatches:
            return

    def _stop_thinking(self) -> None:
        timer = getattr(self, "_thinking_timer", None)
        if timer is not None:
            timer.stop()
            self._thinking_timer = None
        try:
            self.query_one(ThinkingIndicator).hide()
        except NoMatches:
            pass

    def _approval_callback(self, name: str, args: dict) -> bool:
        """给 runtime 使用的审批回调：阻塞等待 TUI 里的 allow/deny 选择。"""

        event = threading.Event()
        decision = {"approved": False}
        try:
            self.call_from_thread(self._show_confirm, name, args, event, decision)
        except RuntimeError:
            return False
        event.wait()
        return bool(decision.get("approved", False))

    def _show_confirm(
        self, name: str, args: dict, event: threading.Event, decision: dict
    ) -> None:
        prompt = ConfirmPrompt(name, format_tool_args(name, args))
        self._confirm_prompt = prompt
        self._confirm_decision = (event, decision)
        chat = self.query_one(ChatLog)
        chat.mount(prompt)
        chat.call_after_refresh(chat.scroll_end, animate=False)

    def _resolve_confirm(self, approved: bool) -> None:
        """用户确认审批后唤醒等待中的工具执行线程。"""

        if self._confirm_decision is None:
            return
        event, decision = self._confirm_decision
        decision["approved"] = bool(approved)
        event.set()
        if self._confirm_prompt is not None:
            self._confirm_prompt.remove()
        self._confirm_prompt = None
        self._confirm_decision = None

    def _ask_user_callback(self, question: str, choices: list[str]) -> str:
        """给 runtime 使用的 ask_user 回调：阻塞等待用户在 TUI 中选择答案。"""

        event = threading.Event()
        decision = {"answer": ""}
        try:
            self.call_from_thread(
                self._show_ask_user, question, choices, event, decision
            )
        except RuntimeError:
            return ""
        event.wait()
        return str(decision.get("answer", ""))

    def _show_ask_user(
        self, question: str, choices: list[str], event: threading.Event, decision: dict
    ) -> None:
        prompt = AskUserPrompt(question, choices)
        self._ask_user_prompt = prompt
        self._ask_user_decision = (event, decision)
        chat = self.query_one(ChatLog)
        chat.mount(prompt)
        chat.call_after_refresh(chat.scroll_end, animate=False)

    def _resolve_ask_user(self, answer: str) -> None:
        """用户回答 ask_user 弹窗后唤醒等待中的 agent 线程。"""

        if self._ask_user_decision is None:
            return
        event, decision = self._ask_user_decision
        decision["answer"] = str(answer)
        event.set()
        if self._ask_user_prompt is not None:
            self._ask_user_prompt.remove()
        self._ask_user_prompt = None
        self._ask_user_decision = None
