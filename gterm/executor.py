import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from gterm.platform_shell import ShellAdapter
from gterm.ui import UIRenderer

_FENCE_RE = re.compile(r"```(?:bash|sh|zsh|shell)?\s*\n(.*?)```", re.DOTALL)
_CLARIFY_RE = re.compile(r"^\s*#\s*CLARIFY:\s*(.+)", re.MULTILINE)
_ANSWER_RE = re.compile(r"^\s*#\s*ANSWER:\s*(.+)", re.MULTILINE | re.DOTALL)

# Commands that need a full TTY — captured subprocess would corrupt their UI.
# These are handed off directly with stdin/stdout/stderr inherited from the terminal.
_TTY_COMMANDS = {
    # AI coding assistants
    "claude",
    "aider",
    "codex",
    "gemini",
    "copilot",
    # editors
    "vim",
    "vi",
    "nvim",
    "nano",
    "emacs",
    "hx",
    "micro",
    # other interactive TUIs
    "less",
    "more",
    "man",
    "top",
    "htop",
    "btop",
    "lazygit",
    "tig",
}

_DANGER_PATTERNS = [
    re.compile(r"\brm\s+(-\w*f\w*\s+)?/"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bformat\b.*\b/dev/"),
    re.compile(r"\bsudo\s+rm\s+-rf\s+[/~]"),
]
_DIRECT_COMMANDS = {
    "bash",
    "brew",
    "bun",
    "cargo",
    "cat",
    "cd",
    "chmod",
    "chown",
    "claude",
    "clear",
    "codex",
    "cp",
    "curl",
    "df",
    "diff",
    "docker",
    "du",
    "echo",
    "env",
    "fd",
    "find",
    "gemini",
    "git",
    "go",
    "grep",
    "head",
    "kubectl",
    "less",
    "ln",
    "ls",
    "make",
    "mkdir",
    "mv",
    "nano",
    "npx",
    "nvim",
    "pip",
    "pip3",
    "pnpm",
    "podman",
    "ps",
    "pwd",
    "py.test",
    "pytest",
    "python",
    "python3",
    "rg",
    "rm",
    "ruff",
    "scp",
    "sed",
    "sh",
    "ssh",
    "tail",
    "tar",
    "touch",
    "top",
    "tree",
    "uv",
    "vi",
    "vim",
    "wget",
    "which",
    "yarn",
    "zsh",
}
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_READ_ONLY_COMMANDS = {
    "awk",
    "cat",
    "column",
    "cut",
    "date",
    "df",
    "diff",
    "du",
    "echo",
    "env",
    "fd",
    "file",
    "find",
    "grep",
    "head",
    "ifconfig",
    "lsof",
    "ls",
    "memory_pressure",
    "netstat",
    "pgrep",
    "printenv",
    "ps",
    "pwd",
    "rg",
    "sed",
    "sort",
    "stat",
    "tail",
    "top",
    "tree",
    "uname",
    "uniq",
    "vm_stat",
    "wc",
    "which",
}
_READ_ONLY_GIT_SUBCOMMANDS = {"diff", "grep", "log", "ls-files", "rev-parse", "show", "status"}
_READ_ONLY_DOCKER_SUBCOMMANDS = {"images", "info", "inspect", "logs", "ps", "stats", "version"}
_READ_ONLY_KUBECTL_SUBCOMMANDS = {"describe", "get", "logs", "version"}
_READ_ONLY_BREW_SUBCOMMANDS = {"info", "list", "search"}


@dataclass(frozen=True)
class CommandPreview:
    info: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    permission_required: bool = True


def is_clarify_response(llm_output: str) -> tuple[bool, str]:
    match = _CLARIFY_RE.search(llm_output)
    if match:
        return True, match.group(1).strip()
    return False, ""


def is_answer_response(llm_output: str) -> tuple[bool, str]:
    match = _ANSWER_RE.search(llm_output)
    if match:
        return True, match.group(1).strip()
    return False, ""


def extract_commands(llm_output: str) -> list[str] | None:
    if is_clarify_response(llm_output)[0] or is_answer_response(llm_output)[0]:
        return None

    match = _FENCE_RE.search(llm_output)
    raw = match.group(1).strip() if match else llm_output.strip()

    lines = [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    return lines if lines else None


def needs_tty(commands: list[str]) -> bool:
    """Return True if any command in the list needs a full TTY (no output capture)."""
    for cmd in commands:
        if _command_needs_tty(cmd):
            return True
    return False


def is_cd_command(command: str) -> tuple[bool, str]:
    parts = command.strip().split(None, 1)
    if parts and parts[0] == "cd":
        return True, parts[1] if len(parts) > 1 else "~"
    return False, ""


def is_dangerous(commands: list[str]) -> bool:
    joined = " ".join(commands)
    return any(p.search(joined) for p in _DANGER_PATTERNS)


def looks_like_direct_command(text: str, cwd: Path) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return False

    words = _split_shell_words(stripped)
    if not words:
        return False

    command_index = 0
    while command_index < len(words) and _ENV_ASSIGNMENT_RE.match(words[command_index]):
        command_index += 1
    if command_index >= len(words):
        return False

    command = words[command_index]
    if _has_shell_syntax(stripped):
        return _looks_runnable(command, cwd)

    if command in _DIRECT_COMMANDS:
        return True

    if command.startswith(("./", "../", "/", "~/")):
        return _path_like_command_exists(command, cwd)

    return len(words[command_index:]) == 1 and shutil.which(command) is not None


def confirm_and_run(
    commands: list[str],
    shell: ShellAdapter,
    ui: UIRenderer,
    cwd: Path,
    paranoid_mode: bool = False,
) -> tuple[bool, str, Path, int]:
    preview = analyze_commands(commands, cwd)

    while True:
        ui.show_command_panel(commands, preview)

        if not preview.permission_required:
            ui.show_info("auto-running read-only command")
            return _execute(commands, shell, ui, cwd)

        if paranoid_mode and is_dangerous(commands):
            ui.show_error(
                "Dangerous command detected. Type the command verbatim to confirm, or 'n' to cancel."
            )
            typed = input("> ").strip()
            if typed != " && ".join(commands):
                ui.show_cancelled()
                return False, "", cwd, 0

        choice = ui.show_confirm_prompt()

        if choice in ("y", "yes", ""):
            return _execute(commands, shell, ui, cwd)
        elif choice in ("n", "no"):
            ui.show_cancelled()
            return False, "", cwd, 0
        elif choice in ("e", "edit"):
            commands = _edit_commands(commands)
        else:
            ui.show_error("Please enter y, n, or e.")


def run_direct_commands(
    commands: list[str],
    shell: ShellAdapter,
    ui: UIRenderer,
    cwd: Path,
) -> tuple[bool, str, Path, int]:
    return _execute(commands, shell, ui, cwd)


def _execute(
    commands: list[str],
    shell: ShellAdapter,
    ui: UIRenderer,
    cwd: Path,
) -> tuple[bool, str, Path, int]:
    if len(commands) == 1:
        is_cd, target = is_cd_command(commands[0])
        if is_cd:
            new_cwd = _resolve_cd(target, cwd)
            ui.show_info(f"cwd → {new_cwd}")
            return True, f"Changed directory to {new_cwd}", new_cwd, 0

    if needs_tty(commands):
        # Peel off any leading `cd` commands to get the effective working directory,
        # then hand off terminal control for the remaining TTY command(s).
        effective_cwd, remaining = _split_leading_cd_commands(commands, cwd)
        launch = " && ".join(remaining) if remaining else commands[-1]
        result = subprocess.run(launch, shell=True, cwd=effective_cwd)
        return True, "", effective_cwd, result.returncode

    exit_code, stdout, stderr = shell.run(commands, cwd=cwd)
    output = stdout + (f"\n[stderr]\n{stderr}" if stderr.strip() else "")
    ui.show_output(output, exit_code)
    return True, output, cwd, exit_code


def _resolve_cd(target: str, cwd: Path) -> Path:
    if target == "~":
        return Path.home()
    p = Path(target)
    if not p.is_absolute():
        p = cwd / p
    resolved = p.resolve()
    return resolved if resolved.is_dir() else cwd


def analyze_commands(commands: list[str], cwd: Path) -> CommandPreview:
    info: list[str] = []
    warnings: list[str] = []
    effective_cwd, _ = _split_leading_cd_commands(commands, cwd)

    if effective_cwd != cwd:
        info.append(f"working directory will change to {effective_cwd}")
    if needs_tty(commands):
        info.append("full terminal handoff; output will not be captured")

    touched_paths: list[str] = []
    saw_file_changes = False
    saw_network = False
    saw_git_mutation = False
    saw_package_change = False
    saw_delete = False
    saw_sudo = False

    for command in commands:
        words = _split_shell_words(command)
        if not words:
            continue

        if words[0] in {"sudo", "doas"}:
            saw_sudo = True
            words = words[1:]
            if not words:
                continue

        if _is_network_command(words):
            saw_network = True
        if _is_file_mutation_command(words, command):
            saw_file_changes = True
            touched_paths.extend(_extract_paths(words, command, effective_cwd))
        if _is_git_mutation_command(words):
            saw_git_mutation = True
        if _is_package_change_command(words):
            saw_package_change = True
        if _is_delete_command(words):
            saw_delete = True

    if saw_file_changes:
        info.append("may modify files on disk")
    if touched_paths:
        unique_paths = list(dict.fromkeys(touched_paths))
        info.append(f"touches paths: {', '.join(unique_paths[:3])}")
    if saw_network:
        info.append("may use the network")
    if saw_git_mutation:
        info.append("modifies git state or working tree")
    if saw_package_change:
        info.append("changes installed packages or project dependencies")

    if saw_sudo:
        warnings.append("runs with elevated privileges")
    if saw_delete:
        warnings.append("deletes files, packages, or other resources")
    if is_dangerous(commands):
        warnings.append("matches a dangerous command pattern")

    permission_required = _requires_confirmation(commands, cwd)
    if not permission_required:
        if needs_tty(commands):
            info.append("non-stateful interactive handoff; will launch without confirmation")
        else:
            info.append("read-only inspection; will run without confirmation")

    return CommandPreview(
        info=info,
        warnings=warnings,
        permission_required=permission_required,
    )


def _split_leading_cd_commands(commands: list[str], cwd: Path) -> tuple[Path, list[str]]:
    effective_cwd = cwd
    remaining: list[str] = []
    for cmd in commands:
        is_cd, target = is_cd_command(cmd)
        if is_cd and not remaining:
            effective_cwd = _resolve_cd(target, effective_cwd)
        else:
            remaining.append(cmd)
    return effective_cwd, remaining


def _split_shell_words(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.strip().split()


def _has_shell_syntax(text: str) -> bool:
    markers = ("|", ">", "<", ";", "&&", "||", "$(", "`")
    return any(marker in text for marker in markers)


def _requires_confirmation(commands: list[str], cwd: Path) -> bool:
    effective_cwd, remaining = _split_leading_cd_commands(commands, cwd)
    if not remaining:
        return False
    return not all(_is_safe_non_stateful_command(command, effective_cwd) for command in remaining)


def _is_safe_non_stateful_command(command: str, cwd: Path) -> bool:
    return _is_safe_read_only_command(command, cwd) or _is_safe_handoff_command(command, cwd)


def _is_safe_read_only_command(command: str, cwd: Path) -> bool:
    stripped = command.strip()
    if not stripped:
        return True

    if any(marker in stripped for marker in (";", "&&", "||", "$(", "`", "&")):
        return False

    if "|" in stripped:
        segments = _split_pipeline_segments(stripped)
        if not segments:
            return False
        return all(_is_safe_read_only_segment(segment, cwd) for segment in segments)

    return _is_safe_read_only_segment(stripped, cwd)


def _is_safe_handoff_command(command: str, cwd: Path) -> bool:
    stripped = command.strip()
    if not stripped:
        return True

    if any(marker in stripped for marker in ("|", ";", "&&", "||", ">", "<", "$(", "`", "&")):
        return False

    words = _split_shell_words(stripped)
    if not words:
        return False

    command_index = 0
    while command_index < len(words) and _ENV_ASSIGNMENT_RE.match(words[command_index]):
        command_index += 1
    if command_index >= len(words):
        return False

    head = words[command_index]
    if head in {"sudo", "doas", "ssh", "scp", "sftp", "rsync"}:
        return False

    return _command_needs_tty(stripped)


def _is_safe_read_only_segment(command: str, cwd: Path) -> bool:
    stripped = command.strip()
    if not stripped or re.search(r"(^|[^>])>>?\s*\S+", stripped):
        return False
    if "<" in stripped:
        return False

    words = _split_shell_words(stripped)
    if not words:
        return False

    command_index = 0
    while command_index < len(words) and _ENV_ASSIGNMENT_RE.match(words[command_index]):
        command_index += 1
    if command_index >= len(words):
        return False

    head = words[command_index]
    args = words[command_index + 1 :]

    if head in {"sudo", "doas", "ssh", "scp", "sftp", "rsync"}:
        return False
    if head.startswith(("./", "../", "/", "~/")) and _path_like_command_exists(head, cwd):
        return False
    if head in _READ_ONLY_COMMANDS:
        return not _command_has_mutating_flags(head, args)
    if head == "git" and args:
        return args[0] in _READ_ONLY_GIT_SUBCOMMANDS
    if head in {"docker", "podman"} and args:
        return args[0] in _READ_ONLY_DOCKER_SUBCOMMANDS
    if head == "kubectl" and args:
        return args[0] in _READ_ONLY_KUBECTL_SUBCOMMANDS
    if head == "brew" and args:
        return args[0] in _READ_ONLY_BREW_SUBCOMMANDS
    if head == "curl":
        return _is_safe_http_read(args)

    return False


def _command_has_mutating_flags(head: str, args: list[str]) -> bool:
    if head == "sed":
        return any(arg.startswith("-i") for arg in args)
    if head in {"find", "fd"}:
        return any(arg in {"-delete", "-exec", "--exec"} for arg in args)
    return False


def _command_needs_tty(command: str) -> bool:
    words = _split_shell_words(command)
    if not words:
        return False

    command_index = 0
    while command_index < len(words) and _ENV_ASSIGNMENT_RE.match(words[command_index]):
        command_index += 1
    if command_index >= len(words):
        return False

    head = words[command_index].lstrip("./")
    args = words[command_index + 1 :]

    if head == "top" and _top_is_noninteractive(args):
        return False

    return head in _TTY_COMMANDS


def _top_is_noninteractive(args: list[str]) -> bool:
    for arg in args:
        if arg in {"-b", "-l"}:
            return True
        if arg.startswith("-b") and arg != "-":
            return True
        if arg.startswith("-l") and arg != "-":
            return True
    return False


def _is_safe_http_read(args: list[str]) -> bool:
    method = "GET"
    for index, arg in enumerate(args):
        if arg in {"-X", "--request"}:
            if index + 1 >= len(args):
                return False
            method = args[index + 1].upper()
        elif arg.startswith("--request="):
            method = arg.split("=", 1)[1].upper()
        elif arg.startswith("-X") and len(arg) > 2:
            method = arg[2:].upper()

        if arg in {
            "-d",
            "--data",
            "--data-raw",
            "--data-binary",
            "--form",
            "-F",
            "--upload-file",
            "-T",
            "-o",
            "--output",
            "-O",
            "--remote-name",
        }:
            return False
        if arg.startswith(("--data=", "--data-raw=", "--data-binary=", "--form=", "--output=")):
            return False

    return method in {"GET", "HEAD"}


def _split_pipeline_segments(command: str) -> list[str]:
    words = _split_shell_words(command)
    if not words:
        return []

    segments: list[str] = []
    current: list[str] = []
    for word in words:
        if word == "|":
            if not current:
                return []
            segments.append(shlex.join(current))
            current = []
            continue
        current.append(word)

    if not current:
        return []
    segments.append(shlex.join(current))
    return segments


def _looks_runnable(command: str, cwd: Path) -> bool:
    if command in _DIRECT_COMMANDS:
        return True
    if command in {".", "source"}:
        return True
    if command.startswith(("./", "../", "/", "~/")):
        return _path_like_command_exists(command, cwd)
    return shutil.which(command) is not None


def _path_like_command_exists(command: str, cwd: Path) -> bool:
    expanded = Path(command).expanduser()
    if not expanded.is_absolute():
        expanded = (cwd / expanded).resolve()
    return expanded.exists()


def _is_network_command(words: list[str]) -> bool:
    head = words[0]
    if head in {"curl", "wget", "scp", "sftp", "ssh"}:
        return True
    if head == "rsync" and any(":" in part for part in words[1:]):
        return True
    if head == "git" and len(words) > 1 and words[1] in {"clone", "fetch", "pull", "push"}:
        return True
    if head in {"docker", "podman"} and len(words) > 1 and words[1] in {"pull", "push", "login"}:
        return True
    return False


def _is_file_mutation_command(words: list[str], command: str) -> bool:
    head = words[0]
    if re.search(r"(^|[^>])>>?\s*\S+", command):
        return True
    if head in {"rm", "mv", "cp", "install", "touch", "mkdir", "rmdir", "tee", "truncate", "dd"}:
        return True
    if head in {"chmod", "chown", "ln", "tar", "unzip", "zip"}:
        return True
    if head == "sed" and any(part.startswith("-i") for part in words[1:]):
        return True
    if (
        head in {"git"}
        and len(words) > 1
        and words[1]
        in {
            "apply",
            "am",
            "checkout",
            "cherry-pick",
            "clean",
            "merge",
            "mv",
            "restore",
            "revert",
            "rm",
            "switch",
        }
    ):
        return True
    return False


def _is_git_mutation_command(words: list[str]) -> bool:
    return (
        words[0] == "git"
        and len(words) > 1
        and words[1]
        in {
            "add",
            "am",
            "apply",
            "checkout",
            "cherry-pick",
            "clean",
            "commit",
            "merge",
            "mv",
            "pull",
            "push",
            "rebase",
            "reset",
            "restore",
            "revert",
            "rm",
            "stash",
            "switch",
            "tag",
        }
    )


def _is_package_change_command(words: list[str]) -> bool:
    head = words[0]
    if head in {"pip", "pip3"} and len(words) > 1 and words[1] in {"install", "uninstall"}:
        return True
    if head == "uv" and len(words) > 1 and words[1] in {"add", "remove", "sync"}:
        return True
    if (
        head == "uv"
        and len(words) > 2
        and words[1] == "pip"
        and words[2] in {"install", "uninstall"}
    ):
        return True
    if (
        head in {"npm", "pnpm", "yarn"}
        and len(words) > 1
        and words[1]
        in {
            "add",
            "install",
            "remove",
            "uninstall",
            "update",
        }
    ):
        return True
    if (
        head in {"brew", "apt", "apt-get"}
        and len(words) > 1
        and words[1]
        in {
            "install",
            "remove",
            "uninstall",
            "upgrade",
        }
    ):
        return True
    if head == "cargo" and len(words) > 1 and words[1] in {"add", "remove", "install"}:
        return True
    if head == "go" and len(words) > 1 and words[1] in {"get", "install"}:
        return True
    return False


def _is_delete_command(words: list[str]) -> bool:
    head = words[0]
    if head in {"rm", "rmdir"}:
        return True
    if head == "git" and len(words) > 1 and words[1] in {"clean", "rm"}:
        return True
    if (
        head in {"docker", "podman"}
        and len(words) > 1
        and words[1]
        in {
            "prune",
            "rm",
            "rmi",
        }
    ):
        return True
    if head == "kubectl" and len(words) > 1 and words[1] == "delete":
        return True
    if (
        head in {"brew", "apt", "apt-get"}
        and len(words) > 1
        and words[1]
        in {
            "remove",
            "uninstall",
        }
    ):
        return True
    if head in {"pip", "pip3"} and len(words) > 1 and words[1] == "uninstall":
        return True
    if (
        head in {"npm", "pnpm", "yarn"}
        and len(words) > 1
        and words[1]
        in {
            "remove",
            "uninstall",
        }
    ):
        return True
    return False


def _extract_paths(words: list[str], command: str, cwd: Path) -> list[str]:
    head = words[0]
    paths: list[str] = []
    if head in {"rm", "mv", "cp", "install", "touch", "mkdir", "rmdir", "chmod", "chown", "ln"}:
        for part in words[1:]:
            if part.startswith("-") or "://" in part or "=" in part:
                continue
            if part in {"--"}:
                continue
            paths.append(_display_path(part, cwd))
    for match in re.finditer(r"(^|[^>])>>?\s*([^\s]+)", command):
        target = match.group(2)
        paths.append(_display_path(target, cwd))
    return paths


def _display_path(raw: str, cwd: Path) -> str:
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate)
    return str((cwd / candidate).resolve())


def _edit_commands(commands: list[str]) -> list[str]:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("\n".join(commands))
        tmp_path = f.name

    os.system(f"{editor} {tmp_path}")

    with open(tmp_path) as f:
        edited = f.read()
    os.unlink(tmp_path)

    lines = [
        ln.strip() for ln in edited.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    return lines if lines else commands
