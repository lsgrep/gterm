import platform
import subprocess
from pathlib import Path
from typing import Protocol


class ShellAdapter(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def os_name(self) -> str: ...

    @property
    def shell_hint(self) -> str: ...

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]: ...


class MacOSShellAdapter:
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

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]:
        combined_cmd = " && ".join(commands)
        result = subprocess.run(
            ["zsh", "-c", combined_cmd],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr


class LinuxShellAdapter:
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

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]:
        combined_cmd = " && ".join(commands)
        result = subprocess.run(
            ["bash", "-c", combined_cmd],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.returncode, result.stdout, result.stderr


def get_shell_adapter() -> ShellAdapter:
    system = platform.system()
    if system == "Darwin":
        return MacOSShellAdapter()
    if system == "Linux":
        return LinuxShellAdapter()
    raise RuntimeError(f"Unsupported platform: {system}")
