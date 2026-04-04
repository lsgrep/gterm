from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

console = Console()


class UIRenderer:
    def show_welcome(self, model_name: str, hw_summary: str, metal_disabled: bool = False) -> None:
        note = ""
        if metal_disabled:
            note = "\n[yellow]⚠ Metal disabled for Gemma 4 (upstream bug) — running on CPU[/]"
        console.print(
            Panel(
                f"[bold green]gterm[/] — natural language terminal\n"
                f"[dim]model : {model_name}[/]\n"
                f"[dim]hw    : {hw_summary}[/]\n"
                f"[dim]type your intent, or /help for commands[/]"
                f"{note}",
                border_style="green",
            )
        )

    def show_help(self) -> None:
        console.print(
            Panel(
                "[bold]/clear[/]    — clear conversation history\n"
                "[bold]/history[/]  — show conversation turns\n"
                "[bold]/cwd[/]      — print current directory\n"
                "[bold]/model[/]    — switch model interactively\n"
                "[bold]/models[/]   — list available models\n"
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
            Panel(f"[yellow]{message}[/]", title="[yellow]clarification needed[/]", border_style="yellow")
        )

    def show_cancelled(self) -> None:
        console.print("[dim]cancelled[/]")

    def show_info(self, message: str) -> None:
        console.print(f"[dim]{message}[/]")

    def show_success(self, message: str) -> None:
        console.print(f"[green]{message}[/]")

    def start_streaming(self) -> Live:
        return Live(Text(""), console=console, refresh_per_second=15)

    def update_stream(self, live: Live, buffer: str) -> None:
        live.update(Text(buffer, style="dim"))

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

    def pick_model(self, models: list, current_path: Path | None, hw_budget_gb: float | None) -> int | None:
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
