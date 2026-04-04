from datetime import date
from pathlib import Path

from gterm.platform_shell import ShellAdapter

SYSTEM_TEMPLATE = """\
You are a shell command assistant running on {os_name}. \
Convert the user's natural language request into shell commands for {shell}.

Rules:
1. Respond ONLY with a single fenced code block using ```{shell_hint} ... ```.
2. Include NO explanation, NO prose, NO apology outside the code block.
3. If the request is unclear, ambiguous, or potentially destructive \
(e.g. deleting files without a path, formatting disks, killing all processes), \
respond with a single line starting with `# CLARIFY:` followed by what you need \
confirmed before proceeding. Do NOT include a code block in this case.
4. Prefer safe flags where available (e.g. `rm -i`, `--dry-run`).
5. For `cd` changes, use `cd <dir>` as the sole command on its own line.

Current working directory: {cwd}
Operating system: {os_name}
Shell: {shell}
Today's date: {date}
"""


class PromptBuilder:
    def __init__(self, shell: ShellAdapter) -> None:
        self._shell = shell

    def build(self, cwd: Path) -> str:
        return SYSTEM_TEMPLATE.format(
            os_name=self._shell.os_name,
            shell=self._shell.name,
            shell_hint=self._shell.shell_hint,
            cwd=cwd,
            date=date.today().isoformat(),
        )
