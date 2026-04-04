from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_ROOT_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
)
_README_NAMES = ("README.md", "README.rst", "README.txt", "README")
_MAX_ITEMS = 8
_MAX_LINE_LENGTH = 220


def build_project_context(cwd: Path) -> str:
    root = find_project_root(cwd)
    if root is None:
        return ""

    lines = ["Current project:", f"- Root: {root}"]
    files = [name for name in _interesting_files(root) if (root / name).exists()]
    if files:
        lines.append(f"- Key files: {', '.join(files)}")

    for summary in (
        _summarize_pyproject(root / "pyproject.toml"),
        _summarize_package_json(root / "package.json"),
        _summarize_cargo_toml(root / "Cargo.toml"),
        _summarize_go_mod(root / "go.mod"),
        _summarize_makefile(root / "Makefile"),
        _summarize_readme(root),
    ):
        lines.extend(summary)

    return "\n".join(_trimmed(line) for line in lines)


def find_project_root(cwd: Path) -> Path | None:
    for candidate in (cwd.resolve(), *cwd.resolve().parents):
        if any((candidate / marker).exists() for marker in _ROOT_MARKERS):
            return candidate
    return None


def _interesting_files(root: Path) -> list[str]:
    names = [
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "docker-compose.yml",
        "compose.yml",
        ".env.example",
    ]
    for readme_name in _README_NAMES:
        if (root / readme_name).exists():
            names.append(readme_name)
            break
    return names


def _summarize_pyproject(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return ["- Python project: pyproject.toml present"]

    project = data.get("project", {})
    lines: list[str] = []
    if name := project.get("name"):
        lines.append(f"- Python project: {name}")
    if scripts := sorted(project.get("scripts", {}).keys()):
        lines.append(f"- Console scripts: {_join_items(scripts)}")
    if groups := sorted(data.get("dependency-groups", {}).keys()):
        lines.append(f"- Dependency groups: {_join_items(groups)}")
    if backend := data.get("build-system", {}).get("build-backend"):
        lines.append(f"- Build backend: {backend}")
    return lines


def _summarize_package_json(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return ["- Node project: package.json present"]

    lines: list[str] = []
    if name := data.get("name"):
        lines.append(f"- Node package: {name}")
    if package_manager := data.get("packageManager"):
        lines.append(f"- Package manager: {package_manager}")
    if scripts := sorted(data.get("scripts", {}).keys()):
        lines.append(f"- Package scripts: {_join_items(scripts)}")
    return lines


def _summarize_cargo_toml(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return ["- Rust project: Cargo.toml present"]

    lines: list[str] = []
    package = data.get("package", {})
    if name := package.get("name"):
        lines.append(f"- Rust crate: {name}")
    if members := data.get("workspace", {}).get("members"):
        lines.append(f"- Workspace members: {_join_items(list(members))}")
    return lines


def _summarize_go_mod(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("module "):
                return [f"- Go module: {line.removeprefix('module ').strip()}"]
    except Exception:
        return ["- Go module: go.mod present"]
    return ["- Go module: go.mod present"]


def _summarize_makefile(path: Path) -> list[str]:
    if not path.exists():
        return []
    targets: list[str] = []
    try:
        for line in path.read_text().splitlines():
            match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(?:\s|$)", line)
            if not match:
                continue
            target = match.group(1)
            if "%" in target or target.startswith("."):
                continue
            targets.append(target)
            if len(targets) >= _MAX_ITEMS:
                break
    except Exception:
        return ["- Makefile: present"]

    return [f"- Make targets: {_join_items(targets)}"] if targets else ["- Makefile: present"]


def _summarize_readme(root: Path) -> list[str]:
    path = next((root / name for name in _README_NAMES if (root / name).exists()), None)
    if path is None:
        return []

    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        return []

    heading = ""
    paragraph_lines: list[str] = []
    in_code_block = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not heading and line.startswith("#"):
            heading = line.lstrip("#").strip()
            continue
        if line and not line.startswith("#"):
            paragraph_lines.append(line)
        elif paragraph_lines:
            break

    summary = " ".join(paragraph_lines)
    results: list[str] = []
    if heading:
        results.append(f"- README title: {heading}")
    if summary:
        results.append(f"- README summary: {_trimmed(summary)}")
    return results


def _join_items(items: list[str]) -> str:
    shown = items[:_MAX_ITEMS]
    suffix = " ..." if len(items) > _MAX_ITEMS else ""
    return ", ".join(shown) + suffix


def _trimmed(text: str) -> str:
    return text if len(text) <= _MAX_LINE_LENGTH else text[: _MAX_LINE_LENGTH - 1] + "…"
