"""Tool abstraction shared by the runtime and prompt builder."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    schema: dict
    description: str
    risky: bool
    runner: Callable[[dict], str]

    @property
    def read_only(self):
        """根据 risky 标记判断工具是否只读。"""
        return not self.risky

    def execute(self, args):
        """执行工具 runner，并统一包装成 ToolResult。"""
        result = self.runner(args)
        if isinstance(result, ToolResult):
            return result
        return ToolResult(content=str(result))

    def __getitem__(self, key):
        """兼容字典式读取工具字段，run 映射到 runner。"""
        if key == "run":
            return self.runner
        return getattr(self, key)
