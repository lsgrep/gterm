from pathlib import Path

from gterm.executor import confirm_and_run


class _FakeShell:
    def __init__(self) -> None:
        self.runs: list[list[str]] = []

    def run(self, commands: list[str], cwd: Path) -> tuple[int, str, str]:
        self.runs.append(commands)
        return 0, "ok\n", ""


class _FakeUI:
    def __init__(self, confirm_choice: str = "n") -> None:
        self.confirm_choice = confirm_choice
        self.confirm_calls = 0
        self.info_messages: list[str] = []
        self.cancelled = False

    def show_command_panel(self, commands, preview) -> None:  # type: ignore[no-untyped-def]
        self.preview = preview

    def show_info(self, message: str) -> None:
        self.info_messages.append(message)

    def show_confirm_prompt(self) -> str:
        self.confirm_calls += 1
        return self.confirm_choice

    def show_cancelled(self) -> None:
        self.cancelled = True

    def show_error(self, message: str) -> None:
        raise AssertionError(message)

    def show_output(self, output: str, exit_code: int) -> None:
        self.output = (output, exit_code)


def test_confirm_and_run_auto_executes_read_only_commands() -> None:
    shell = _FakeShell()
    ui = _FakeUI()

    was_run, output, new_cwd, exit_code = confirm_and_run(
        ["pwd"],
        shell,
        ui,
        Path.cwd(),
    )

    assert was_run is True
    assert output == "ok\n"
    assert new_cwd == Path.cwd()
    assert exit_code == 0
    assert shell.runs == [["pwd"]]
    assert ui.confirm_calls == 0
    assert "auto-running read-only command" in ui.info_messages


def test_confirm_and_run_still_prompts_for_stateful_commands(tmp_path: Path) -> None:
    shell = _FakeShell()
    ui = _FakeUI(confirm_choice="n")

    was_run, output, new_cwd, exit_code = confirm_and_run(
        ["touch created.txt"],
        shell,
        ui,
        tmp_path,
    )

    assert was_run is False
    assert output == ""
    assert new_cwd == tmp_path
    assert exit_code == 0
    assert shell.runs == []
    assert ui.confirm_calls == 1
    assert ui.cancelled is True


def test_confirm_and_run_auto_executes_non_stateful_handoff(monkeypatch, tmp_path: Path) -> None:
    class _TTYResult:
        returncode = 0

    shell = _FakeShell()
    ui = _FakeUI()
    calls: list[tuple[str, Path]] = []

    def fake_subprocess_run(command: str, shell: bool, cwd: Path) -> _TTYResult:
        calls.append((command, cwd))
        return _TTYResult()

    monkeypatch.setattr("gterm.executor.subprocess.run", fake_subprocess_run)

    was_run, output, new_cwd, exit_code = confirm_and_run(
        [f"cd {tmp_path}", "codex"],
        shell,
        ui,
        Path.cwd(),
    )

    assert was_run is True
    assert output == ""
    assert new_cwd == tmp_path
    assert exit_code == 0
    assert shell.runs == []
    assert ui.confirm_calls == 0
    assert calls == [("codex", tmp_path)]
