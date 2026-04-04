"""Parse shell history to extract visited directories and detect project roots."""

from __future__ import annotations

import re
from pathlib import Path

_ZSH_HIST = Path.home() / ".zsh_history"
_BASH_HIST = Path.home() / ".bash_history"

# Match `cd <path>` possibly preceded by && or ;
# Captures shell-escaped paths like /Library/Application\ Support
_CD_RE = re.compile(r"(?:^|&&|;)\s*cd\s+((?:[^\s;&|>\\]|\\.)+)")

_PROJECT_MARKERS: dict[str, str] = {
    ".git": "git",
    "pyproject.toml": "python",
    "package.json": "node",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "build.gradle": "java",
    "CMakeLists.txt": "cmake",
    "Makefile": "make",
}


def _read_history_lines(limit: int) -> list[str]:
    for hist_file in (_ZSH_HIST, _BASH_HIST):
        if not hist_file.exists():
            continue
        try:
            raw = hist_file.read_bytes().decode("utf-8", errors="replace")
            lines = raw.splitlines()[-limit:]
            result: list[str] = []
            for line in lines:
                # zsh extended history format: ': timestamp:elapsed;command'
                if line.startswith(": ") and ";" in line:
                    _, _, cmd = line.partition(";")
                    result.append(cmd)
                else:
                    result.append(line)
            return result
        except OSError:
            pass
    return []


def extract_dir_visits(limit: int = 10000) -> dict[str, int]:
    """Return {absolute_path: visit_count} extracted from cd commands in shell history."""
    home = str(Path.home())
    counts: dict[str, int] = {}

    for line in _read_history_lines(limit):
        for m in _CD_RE.finditer(line):
            raw = m.group(1).strip().strip("'\"")
            # un-escape backslash-escaped characters (e.g. Application\ Support)
            raw = re.sub(r"\\(.)", r"\1", raw)
            if not raw or raw in ("-", "--", ".."):
                continue
            if raw.startswith("~"):
                raw = home + raw[1:]
            if not raw.startswith("/"):
                continue  # skip relative paths — no cwd context available
            counts[raw] = counts.get(raw, 0) + 1

    return counts


def detect_project_type(path: Path) -> str | None:
    """Return project type if path looks like a project root, else None."""
    for marker, ptype in _PROJECT_MARKERS.items():
        if (path / marker).exists():
            return ptype
    return None
