from pathlib import Path

from gterm.prompt import PromptBuilder


class _FakeShell:
    name = "zsh"
    os_name = "macOS"
    shell_hint = "bash"
    command_notes = "Use standard shell tools."


def test_prompt_allows_direct_answers_for_generic_questions() -> None:
    prompt = PromptBuilder(_FakeShell()).build(Path.cwd())

    assert "answer questions directly when command execution is unnecessary" in prompt
    assert "capability overview" in prompt
    assert "Do NOT force shell commands when the user is asking a generic or conceptual question." in prompt
    assert '"what can you do?"' in prompt
