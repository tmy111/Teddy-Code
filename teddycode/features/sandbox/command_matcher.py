"""Command pattern matching for sandbox exclusions."""

from fnmatch import fnmatch


def command_is_excluded(command, patterns):  # Return the command is excluded.
    command = str(command or "").strip()
    return any(fnmatch(command, str(pattern)) for pattern in patterns or ())
