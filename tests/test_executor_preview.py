from pathlib import Path

from gterm.executor import analyze_commands


def test_analyze_commands_reports_risks_and_context() -> None:
    tmp_dir = Path("/tmp").resolve()
    preview = analyze_commands(
        ["cd /tmp", "sudo rm -rf build", "curl -fsSL https://example.com > out.txt"],
        Path.cwd(),
    )

    assert any(f"working directory will change to {tmp_dir}" in item for item in preview.info)
    assert any("may modify files on disk" in item for item in preview.info)
    assert any("may use the network" in item for item in preview.info)
    assert any("runs with elevated privileges" in item for item in preview.warnings)
    assert any("deletes files, packages, or other resources" in item for item in preview.warnings)


def test_analyze_commands_flags_tty_git_and_package_changes() -> None:
    preview = analyze_commands(
        ["git commit -am 'save it'", "uv add rich", "codex"],
        Path.cwd(),
    )

    assert any("full terminal handoff" in item for item in preview.info)
    assert any("modifies git state or working tree" in item for item in preview.info)
    assert any("changes installed packages or project dependencies" in item for item in preview.info)
