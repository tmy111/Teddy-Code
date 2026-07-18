"""Optional shell sandbox runner."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from shutil import which as default_which

from .checker import SandboxChecker
from .command_matcher import command_is_excluded
from .config import SandboxConfig


class SandboxRunner:
    def __init__(self, config=None, *, which=None, run=None, emit_event=None):
        self.config = config or SandboxConfig()
        self.which = which or default_which
        self.run_process = run
        self.emit_event = emit_event or (lambda event, payload: None)

    def run(self, command, *, cwd, env, timeout):
        config = self.config
        if config.mode == "off" or (
            config.mode != "required"
            and command_is_excluded(command, config.excluded_commands)
        ):
            return self._plain(command, cwd=cwd, env=env, timeout=timeout)

        backend_path = SandboxChecker(self.which).backend_path(config.backend)
        if not backend_path:
            self.emit_event(
                "sandbox_unavailable",
                {
                    "mode": config.mode,
                    "backend": config.backend,
                    "command": str(command or "")[:200],
                },
            )
            if config.mode == "required":
                raise RuntimeError("sandbox required but unavailable")
            return self._plain(command, cwd=cwd, env=env, timeout=timeout)

        argv = self._bubblewrap_argv(backend_path, command, Path(cwd), config)
        run_process = self.run_process or subprocess.run
        return run_process(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env
        )

    def _plain(self, command, *, cwd, env, timeout):
        run_process = self.run_process or subprocess.run
        shell_command = command
        shell_kwargs = {"shell": True}
        if os.name == "nt":
            quoted_executable = re.match(r"^'([^']+)'(?:\s+(.*))?$", str(command), re.DOTALL)
            if quoted_executable:
                tail = quoted_executable.group(2) or ""
                shell_command = [quoted_executable.group(1), *shlex.split(tail)]
                shell_kwargs = {"shell": False}
            elif self._looks_like_windows_executable(str(command)):
                shell_command = self._split_windows_args(str(command))
                shell_kwargs = {"shell": False}
            elif self._looks_like_python_command(str(command)):
                shell_command = self._python_argv(str(command))
                shell_kwargs = {"shell": False}
            else:
                shell_command = [r"C:\Windows\System32\cmd.exe", "/d", "/c", str(command)]
                shell_kwargs = {"shell": False}
        return run_process(
            shell_command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            **shell_kwargs,
        )

    @staticmethod
    def _looks_like_windows_executable(command):
        parts = shlex.split(command, posix=False)
        return bool(parts and parts[0].lower().endswith((".exe", ".bat", ".cmd")))

    @staticmethod
    def _looks_like_python_command(command):
        parts = shlex.split(command, posix=False)
        return bool(parts and parts[0].lower() in {"python", "python3"})

    @staticmethod
    def _python_argv(command):
        parts = SandboxRunner._split_windows_args(command)
        return [sys.executable, *parts[1:]]

    @staticmethod
    def _split_windows_args(command):
        return [
            part[1:-1] if len(part) > 1 and part[0] == part[-1] and part[0] in {"'", '"'} else part
            for part in shlex.split(command, posix=False)
        ]

    def _bubblewrap_argv(self, backend_path, command, cwd, config):
        argv = [
            backend_path,
            "--die-with-parent",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
        ]
        bind_mode = "--bind" if config.workspace_write else "--ro-bind"
        argv.extend([bind_mode, str(cwd), str(cwd)])
        for path in config.extra_readonly_paths:
            argv.extend(["--ro-bind", path, path])
        for path in (*config.deny_read, *config.deny_write):
            argv.extend(["--tmpfs", path])
        argv.extend(["--chdir", str(cwd), "--", "/bin/sh", "-lc", str(command)])
        return argv
