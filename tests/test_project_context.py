from pathlib import Path

from gterm.project_context import build_project_context


def test_build_project_context_summarizes_python_repo(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "README.md").write_text(
        "# Demo\n\nA local CLI for testing repo-aware prompts.\n\n## Usage\n\nStuff.\n"
    )
    (root / "pyproject.toml").write_text(
        """
[project]
name = "demo-cli"

[project.scripts]
demo = "demo.cli:main"

[build-system]
build-backend = "hatchling.build"

[dependency-groups]
dev = ["pytest"]
docs = ["mkdocs"]
""".strip()
    )
    (root / "Makefile").write_text("test:\n\tpytest\nlint:\n\truff check .\n")

    context = build_project_context(root / "src")

    assert "Current project:" in context
    assert f"- Root: {root}" in context
    assert "- Python project: demo-cli" in context
    assert "- Console scripts: demo" in context
    assert "- Dependency groups: dev, docs" in context
    assert "- Build backend: hatchling.build" in context
    assert "- Make targets: test, lint" in context
    assert "- README summary: A local CLI for testing repo-aware prompts." in context


def test_build_project_context_summarizes_node_repo(tmp_path: Path) -> None:
    root = tmp_path / "webapp"
    root.mkdir()
    (root / "package.json").write_text(
        """
{
  "name": "webapp",
  "packageManager": "pnpm@9.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest"
  }
}
""".strip()
    )

    context = build_project_context(root)

    assert "- Node package: webapp" in context
    assert "- Package manager: pnpm@9.0.0" in context
    assert "- Package scripts: build, dev, test" in context
