"""Persist and manage user context derived from shell history."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from gterm.shell_history import detect_project_type, extract_dir_visits

_STATE_FILE = Path.home() / ".config" / "gterm" / "state.json"
_MAX_PROJECTS = 30
_MAX_RECENT_DIRS = 20


@dataclass
class ProjectEntry:
    name: str
    path: str
    type: str
    visit_count: int = 1


@dataclass
class ContextState:
    last_updated: str = ""
    projects: list[ProjectEntry] = field(default_factory=list)
    recent_dirs: list[str] = field(default_factory=list)
    history_consent: bool | None = None  # None = not yet asked
    model_arch_cache: dict[str, str] = field(default_factory=dict)  # model_path → arch

    def format_for_prompt(self) -> str:
        if not self.projects and not self.recent_dirs:
            return ""
        lines: list[str] = []
        if self.projects:
            lines.append("Known projects (from shell history):")
            for p in self.projects[:_MAX_PROJECTS]:
                lines.append(f"  - {p.name} [{p.type}] → {p.path}")
        if self.recent_dirs:
            lines.append("Frequent directories:")
            for d in self.recent_dirs[:10]:
                lines.append(f"  - {d}")
        return "\n".join(lines)


def load_state() -> ContextState:
    if not _STATE_FILE.exists():
        return ContextState()
    try:
        data = json.loads(_STATE_FILE.read_text())
        projects = [ProjectEntry(**p) for p in data.get("projects", [])]
        consent = data.get("history_consent", None)
        return ContextState(
            last_updated=data.get("last_updated", ""),
            projects=projects,
            recent_dirs=data.get("recent_dirs", []),
            history_consent=consent,
            model_arch_cache=data.get("model_arch_cache", {}),
        )
    except Exception:
        return ContextState()


def set_consent(granted: bool) -> None:
    """Persist the user's history-consent decision without touching other state."""
    state = load_state()
    state.history_consent = granted
    _save_state(state)


def update_state() -> ContextState:
    """Parse shell history, refresh project/dir list, save and return updated state."""
    existing = load_state()
    dir_visits = extract_dir_visits()

    existing_projects: dict[str, ProjectEntry] = {p.path: p for p in existing.projects}

    for raw_path, count in dir_visits.items():
        path = Path(raw_path)
        if not path.is_dir():
            continue
        ptype = detect_project_type(path)
        if ptype is None:
            continue
        if raw_path in existing_projects:
            existing_projects[raw_path].visit_count += count
        else:
            existing_projects[raw_path] = ProjectEntry(
                name=path.name,
                path=raw_path,
                type=ptype,
                visit_count=count,
            )

    top_dirs = sorted(dir_visits.items(), key=lambda x: -x[1])
    recent_dirs = [p for p, _ in top_dirs if Path(p).is_dir()][:_MAX_RECENT_DIRS]

    projects = sorted(existing_projects.values(), key=lambda p: -p.visit_count)[:_MAX_PROJECTS]

    state = ContextState(
        last_updated=datetime.now(timezone.utc).isoformat(),
        projects=projects,
        recent_dirs=recent_dirs,
    )
    _save_state(state)
    return state


def cache_model_arch(model_path: str, arch: str) -> None:
    """Persist arch string for model_path so we avoid re-loading on next startup."""
    state = load_state()
    state.model_arch_cache[model_path] = arch
    _save_state(state)


def get_cached_arch(model_path: str) -> str | None:
    return load_state().model_arch_cache.get(model_path)


def _save_state(state: ContextState) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "last_updated": state.last_updated,
        "history_consent": state.history_consent,
        "model_arch_cache": state.model_arch_cache,
        "projects": [asdict(p) for p in state.projects],
        "recent_dirs": state.recent_dirs,
    }
    _STATE_FILE.write_text(json.dumps(data, indent=2))
