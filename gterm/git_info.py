"""Lightweight git status detection for the prompt line."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitStatus:
    branch: str
    dirty: bool
    ahead: int = 0
    behind: int = 0


def get_git_status(cwd: Path) -> GitStatus | None:
    """Return git status for cwd, or None if not inside a repo."""
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None

    try:
        porcelain = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        dirty = bool(porcelain.strip())
    except Exception:
        dirty = False

    try:
        counts = (
            subprocess.check_output(
                ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                cwd=cwd,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            .strip()
            .split()
        )
        ahead = int(counts[0]) if counts else 0
        behind = int(counts[1]) if len(counts) > 1 else 0
    except Exception:
        ahead = behind = 0

    return GitStatus(branch=branch, dirty=dirty, ahead=ahead, behind=behind)
