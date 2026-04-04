import os
import re
import tempfile
from pathlib import Path

from gterm.platform_shell import ShellAdapter
from gterm.ui import UIRenderer

_FENCE_RE = re.compile(r"```(?:bash|sh|zsh|shell)?\s*\n(.*?)```", re.DOTALL)
_CLARIFY_RE = re.compile(r"^\s*#\s*CLARIFY:\s*(.+)", re.MULTILINE)

_DANGER_PATTERNS = [
    re.compile(r"\brm\s+(-\w*f\w*\s+)?/"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bformat\b.*\b/dev/"),
    re.compile(r"\bsudo\s+rm\s+-rf\s+[/~]"),
]


def extract_commands(llm_output: str) -> list[str] | None:
    if is_clarify_response(llm_output)[0]:
        return None

    match = _FENCE_RE.search(llm_output)
    raw = match.group(1).strip() if match else llm_output.strip()

    lines = [l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
    return lines if lines else None


def is_clarify_response(llm_output: str) -> tuple[bool, str]:
    match = _CLARIFY_RE.search(llm_output)
    if match:
        return True, match.group(1).strip()
    return False, ""


def is_cd_command(command: str) -> tuple[bool, str]:
    parts = command.strip().split(None, 1)
    if parts and parts[0] == "cd":
        return True, parts[1] if len(parts) > 1 else "~"
    return False, ""


def is_dangerous(commands: list[str]) -> bool:
    joined = " ".join(commands)
    return any(p.search(joined) for p in _DANGER_PATTERNS)


def confirm_and_run(
    commands: list[str],
    shell: ShellAdapter,
    ui: UIRenderer,
    cwd: Path,
    paranoid_mode: bool = False,
) -> tuple[bool, str, Path]:
    while True:
        ui.show_command_panel(commands)

        if paranoid_mode and is_dangerous(commands):
            ui.show_error("Dangerous command detected. Type the command verbatim to confirm, or 'n' to cancel.")
            typed = input("> ").strip()
            if typed != " && ".join(commands):
                ui.show_cancelled()
                return False, "", cwd

        choice = ui.show_confirm_prompt()

        if choice in ("y", "yes", ""):
            return _execute(commands, shell, ui, cwd)
        elif choice in ("n", "no"):
            ui.show_cancelled()
            return False, "", cwd
        elif choice in ("e", "edit"):
            commands = _edit_commands(commands)
        else:
            ui.show_error("Please enter y, n, or e.")


def _execute(
    commands: list[str],
    shell: ShellAdapter,
    ui: UIRenderer,
    cwd: Path,
) -> tuple[bool, str, Path]:
    if len(commands) == 1:
        is_cd, target = is_cd_command(commands[0])
        if is_cd:
            new_cwd = _resolve_cd(target, cwd)
            ui.show_info(f"cwd → {new_cwd}")
            return True, f"Changed directory to {new_cwd}", new_cwd

    exit_code, stdout, stderr = shell.run(commands, cwd=cwd)
    output = stdout + (f"\n[stderr]\n{stderr}" if stderr.strip() else "")
    ui.show_output(output, exit_code)
    return True, output, cwd


def _resolve_cd(target: str, cwd: Path) -> Path:
    if target == "~":
        return Path.home()
    p = Path(target)
    if not p.is_absolute():
        p = cwd / p
    resolved = p.resolve()
    return resolved if resolved.is_dir() else cwd


def _edit_commands(commands: list[str]) -> list[str]:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("\n".join(commands))
        tmp_path = f.name

    os.system(f"{editor} {tmp_path}")

    with open(tmp_path) as f:
        edited = f.read()
    os.unlink(tmp_path)

    lines = [l.strip() for l in edited.splitlines() if l.strip() and not l.strip().startswith("#")]
    return lines if lines else commands
