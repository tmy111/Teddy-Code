"""Sandbox backend availability checks."""


class SandboxChecker:
    def __init__(self, which):  # Initialize the instance.
        self.which = which

    def backend_path(self, backend):  # Return the backend path.
        backend = "bubblewrap" if backend == "auto" else backend
        if backend in {"none", "off"}:
            return ""
        if backend == "bubblewrap":
            return self.which("bwrap") or ""
        return ""
