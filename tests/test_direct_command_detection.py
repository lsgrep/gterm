from pathlib import Path

from gterm.executor import looks_like_direct_command


def test_looks_like_direct_command_accepts_common_shell_inputs(tmp_path: Path) -> None:
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\necho hi\n")

    assert looks_like_direct_command("git status", Path.cwd())
    assert looks_like_direct_command("make run", Path.cwd())
    assert looks_like_direct_command("uv run pytest -q", Path.cwd())
    assert looks_like_direct_command("cd ..", Path.cwd())
    assert looks_like_direct_command(f"{script}", Path.cwd())
    assert looks_like_direct_command("FOO=1 python -V", Path.cwd())
    assert looks_like_direct_command("cat README.md | head -n 5", Path.cwd())


def test_looks_like_direct_command_rejects_plain_english_requests() -> None:
    cwd = Path.cwd()

    assert not looks_like_direct_command("what are you", cwd)
    assert not looks_like_direct_command("what could you do?", cwd)
    assert not looks_like_direct_command("show me memory usage", cwd)
    assert not looks_like_direct_command("please run git status", cwd)
    assert not looks_like_direct_command("open my overlay-web project in codex", cwd)
