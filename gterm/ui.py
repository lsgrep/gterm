from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from gterm.git_info import GitStatus

console = Console()


def _abbrev_path(p: Path) -> str:
    """Replace home directory prefix with ~."""
    try:
        return "~/" + str(p.relative_to(Path.home()))
    except ValueError:
        return str(p)


class UIRenderer:
    def print_prompt_line(self, cwd: Path, git: GitStatus | None) -> None:
        """Print the decorative status line above the input cursor."""
        path_str = _abbrev_path(cwd)

        line = Text()
        line.append("  ", style="")
        line.append(path_str, style="bold cyan")

        if git:
            line.append("  ", style="")
            if git.dirty:
                line.append(f" {git.branch}", style="bold yellow")
                line.append(" ●", style="yellow")
            else:
                line.append(f" {git.branch}", style="bold green")
                line.append(" ✓", style="green")
            if git.ahead:
                line.append(f" ↑{git.ahead}", style="dim cyan")
            if git.behind:
                line.append(f" ↓{git.behind}", style="dim red")

        line.append("  ", style="")
        line.append("gterm", style="dim green")
        console.print(line)

    def show_welcome(self, model_name: str, hw_summary: str, metal_disabled: bool = False) -> None:
        lines = [
            "[bold green]gterm[/]  [dim]natural language terminal[/]",
            f"[dim]  model  [/][cyan]{model_name}[/]",
            f"[dim]  hw     [/][dim]{hw_summary}[/]",
            "[dim]  /help for commands · exit to quit[/]",
        ]
        if metal_disabled:
            lines.append("[yellow]  ⚠ Metal disabled for Gemma 4 (upstream bug) — CPU only[/]")
        console.print(Panel("\n".join(lines), border_style="dim green", padding=(0, 1)))

    def show_help(self) -> None:
        console.print(
            Panel(
                "[bold]/clear[/]    — clear conversation history\n"
                "[bold]/history[/]  — show conversation turns\n"
                "[bold]/cwd[/]      — print current directory\n"
                "[bold]/model[/]    — switch model interactively\n"
                "[bold]/models[/]   — list available models\n"
                "[bold]/init[/]     — rebuild context from shell history\n"
                "[bold]/help[/]     — show this message\n"
                "[bold]exit[/]      — quit (also Ctrl-D)",
                title="commands",
                border_style="dim",
            )
        )

    def show_command_panel(self, commands: list[str]) -> None:
        code = "\n".join(commands)
        syntax = Syntax(code, "bash", theme="monokai", word_wrap=True)
        console.print(Panel(syntax, title="[yellow]proposed command[/]", border_style="yellow"))

    def show_confirm_prompt(self) -> str:
        console.print("[dim]  \\[y]es  \\[n]o  \\[e]dit[/]  ", end="")
        return input().strip().lower()

    def show_output(self, output: str, exit_code: int) -> None:
        if not output.strip():
            return
        color = "green" if exit_code == 0 else "red"
        label = "output" if exit_code == 0 else f"error (exit {exit_code})"
        console.print(Panel(output.rstrip(), title=f"[{color}]{label}[/]", border_style=color))

    def show_error(self, message: str) -> None:
        console.print(f"[red]error:[/] {message}")

    def show_clarify(self, message: str) -> None:
        console.print(
            Panel(
                f"[yellow]{message}[/]",
                title="[yellow]clarification needed[/]",
                border_style="yellow",
            )
        )

    def show_answer(self, message: str) -> None:
        console.print(Panel(message, title="[cyan]answer[/]", border_style="cyan"))

    def console_print(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        console.print(*args, **kwargs)

    def show_cancelled(self) -> None:
        console.print("[dim]cancelled[/]")

    def show_info(self, message: str) -> None:
        console.print(f"[dim]{message}[/]")

    def show_success(self, message: str) -> None:
        console.print(f"[green]{message}[/]")

    def start_streaming(self) -> Live:
        return Live(
            Spinner("dots", text=" thinking…", style="dim"),
            console=console,
            refresh_per_second=15,
            transient=True,  # erase spinner/stream when done — only the result panel stays
        )

    def update_stream(self, live: Live, buffer: str) -> None:
        live.update(Text(buffer, style="dim"))

    def show_followup(self, message: str) -> None:
        console.print(Panel(message, title="[dim]insight[/]", border_style="dim"))

    def show_history(self, turns: list[tuple[str, str]]) -> None:
        if not turns:
            console.print("[dim]no history[/]")
            return
        for i, (user, assistant) in enumerate(turns, 1):
            console.print(f"[bold]{i}.[/] [cyan]{user}[/]")
            if assistant:
                short = assistant[:120] + "…" if len(assistant) > 120 else assistant
                console.print(f"   [dim]{short}[/]")

    def show_model_table(
        self,
        models: list,
        current_path: Path | None = None,
        hw_budget_gb: float | None = None,
    ) -> None:
        from gterm.model_manager import get_local_model_path, is_downloaded

        table = Table(title="Available Models", border_style="dim")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Name", style="bold")
        table.add_column("Quant", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Min RAM", justify="right")
        table.add_column("Fits", justify="center")
        table.add_column("Status")

        for i, m in enumerate(models, 1):
            downloaded = is_downloaded(m)
            active = current_path and current_path == get_local_model_path(m)
            fits = hw_budget_gb is None or m.size_gb <= hw_budget_gb
            fits_str = "[green]✓[/]" if fits else "[dim]✗[/]"

            if active:
                status = "[green]active[/]"
            elif downloaded:
                status = "[blue]downloaded[/]"
            else:
                status = "[dim]not downloaded[/]"

            table.add_row(
                str(i),
                m.name,
                m.quant,
                f"{m.size_gb:.1f}GB",
                f"{m.min_ram_gb:.0f}GB",
                fits_str,
                status,
            )

        console.print(table)

    def pick_model(
        self, models: list, current_path: Path | None, hw_budget_gb: float | None
    ) -> int | None:
        """Show model table and return 0-based index of chosen model, or None to cancel."""
        self.show_model_table(models, current_path, hw_budget_gb)
        console.print("[dim]Enter # to switch, or press Enter to cancel:[/] ", end="")
        raw = input().strip()
        if not raw:
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(models):
                return idx
            self.show_error(f"Out of range. Enter 1–{len(models)}.")
        except ValueError:
            self.show_error("Enter a number.")
        return None

    def confirm_download(self, model_name: str, size_gb: float) -> bool:
        console.print(
            Panel(
                f"[bold]{model_name}[/] ({size_gb:.1f}GB)\n"
                f"[dim]This will be saved to ~/.config/gterm/models/[/]",
                title="[cyan]download model?[/]",
                border_style="cyan",
            )
        )
        console.print("[dim]  \\[y]es  \\[n]o[/]  ", end="")
        return input().strip().lower() in ("y", "yes", "")
