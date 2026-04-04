from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Protocol

# Matches valid env var names (ASCII identifiers, may contain dots for some tools)
_ENV_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)")


def _capture_login_env(shell: str) -> dict[str, str]:
    """Run a login shell and capture its exported environment.

    Uses `env -0` (null-separated) to safely handle values containing newlines.
    Falls back to newline parsing if env -0 isn't available.
    """
    # Try null-separated first (handles multi-line values correctly)
    for cmd in ("env -0", "env"):
        try:
            result = subprocess.run(
                [shell, "-l", "-c", cmd],
                capture_output=True,
                timeout=5,
                stderr=subprocess.DEVNULL,
            )
            raw = result.stdout
            if not raw:
                continue

            env: dict[str, str] = {}
            separator = b"\0" if cmd == "env -0" else b"\n"
            for item in raw.split(separator):
                text = item.decode("utf-8", errors="replace")
                m = _ENV_LINE_RE.match(text)
                if m:
                    env[m.group(1)] = text[len(m.group(1)) + 1 :]
            if env:
                return env
        except Exception:
            continue

    return dict(os.environ)


class ShellAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def os_name(self) -> str: ...

    @property
    def shell_hint(self) -> str: ...

    @property
    def command_notes(self) -> str: ...

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]: ...


class MacOSShellAdapter:
    def __init__(self) -> None:
        self._env = _capture_login_env("/bin/zsh")

    @property
    def name(self) -> str:
        return "zsh"

    @property
    def os_name(self) -> str:
        ver = platform.mac_ver()[0]
        return f"macOS {ver}" if ver else "macOS"

    @property
    def shell_hint(self) -> str:
        return "bash"

    @property
    def command_notes(self) -> str:
        return (
            "macOS-specific commands and patterns:\n"
            "\n"
            "MEMORY:\n"
            "- Overview:       top -l 1 -s 0 | grep -E 'PhysMem|Swap'\n"
            "- Detailed stats: vm_stat\n"
            "- Pressure:       memory_pressure\n"
            "- Top consumers:  ps aux -m | awk 'NR==1 || NR<=15' | column -t\n"
            "\n"
            "CPU:\n"
            "- Snapshot:       top -l 1 -s 0 | grep -E 'CPU|Load'\n"
            "- Top processes:  ps aux -r | awk 'NR==1 || NR<=15' | column -t\n"
            "\n"
            "DISK:\n"
            "- Usage:          df -h\n"
            "- Dir size:       du -sh <dir>\n"
            "- Largest items:  du -sh * | sort -rh | head -20\n"
            "\n"
            "NETWORK:\n"
            "- Open ports:     lsof -iTCP -sTCP:LISTEN -n -P\n"
            "- Connections:    netstat -an -p tcp | grep ESTABLISHED\n"
            "- Interface info: ifconfig en0\n"
            "\n"
            "PROCESSES:\n"
            "- All processes:  ps aux | column -t\n"
            "- Find by name:   pgrep -l <name>\n"
            "- Kill by name:   pkill <name>\n"
            "\n"
            "BSD vs GNU gotchas:\n"
            "- sed in-place:   sed -i '' 's/a/b/' file  (empty string required)\n"
            "- date:           no -d flag; use date -v+1d for arithmetic\n"
            "- grep:           no -P flag; use -E for extended regex\n"
            "- top -o:         key is 'mem' or 'cpu' (not '%MEM')\n"
            "- ps --sort:      not supported; use -r (CPU) or -m (memory)"
        )

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]:
        combined_cmd = " && ".join(commands)
        result = subprocess.run(
            ["zsh", "-c", combined_cmd],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=self._env,
        )
        return result.returncode, result.stdout, result.stderr


class LinuxShellAdapter:
    def __init__(self) -> None:
        self._env = _capture_login_env("/bin/bash")

    @property
    def name(self) -> str:
        return "bash"

    @property
    def os_name(self) -> str:
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "Linux"

    @property
    def shell_hint(self) -> str:
        return "bash"

    @property
    def command_notes(self) -> str:
        return (
            "Linux uses GNU tools:\n"
            "- `top`: sort by memory with `top -o %MEM -bn1`\n"
            "- `ps`: sort by memory with `ps aux --sort=-%mem`\n"
            "- `sed`: in-place edit with `sed -i 's/a/b/' file`"
        )

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]:
        combined_cmd = " && ".join(commands)
        result = subprocess.run(
            ["bash", "-c", combined_cmd],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=self._env,
        )
        return result.returncode, result.stdout, result.stderr


def get_shell_adapter() -> ShellAdapter:
    system = platform.system()
    if system == "Darwin":
        return MacOSShellAdapter()
    if system == "Linux":
        return LinuxShellAdapter()
    raise RuntimeError(f"Unsupported platform: {system}")
