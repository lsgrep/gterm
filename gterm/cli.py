import sys
from pathlib import Path

import click

from gterm.config import Settings, load_settings, save_default_model
from gterm.hardware import detect_hardware
from gterm.history import ConversationHistory
from gterm.llm import LLMClient
from gterm.model_manager import (
    ModelVariant,
    download_model,
    get_local_model_path,
    is_downloaded,
    list_models,
    recommend_model,
)
from gterm.platform_shell import get_shell_adapter
from gterm.prompt import PromptBuilder
from gterm.repl import GtermREPL
from gterm.ui import UIRenderer


@click.group(invoke_without_command=True)
@click.option("--model", "model_path", type=click.Path(exists=True, path_type=Path), help="Path to a .gguf model file")
@click.option("--ctx", "n_ctx", type=int, default=None, help="Context window size (default: 8192)")
@click.option("--gpu-layers", "n_gpu_layers", type=int, default=None, help="GPU layers (-1=all, 0=CPU only)")
@click.option("--paranoid", is_flag=True, default=False, help="Extra confirmation for dangerous commands")
@click.pass_context
def main(
    ctx: click.Context,
    model_path: Path | None,
    n_ctx: int | None,
    n_gpu_layers: int | None,
    paranoid: bool,
) -> None:
    """gterm — natural language terminal powered by Gemma 4."""
    if ctx.invoked_subcommand is not None:
        return

    ui = UIRenderer()
    hw = detect_hardware()

    resolved_model = _resolve_model(model_path, ui, hw)
    if resolved_model is None:
        sys.exit(1)

    try:
        settings = load_settings(
            model_path=resolved_model,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            paranoid_mode=paranoid if paranoid else None,
        )
    except Exception as e:
        ui.show_error(str(e))
        sys.exit(1)

    ui.show_info("Loading model…")
    try:
        llm = LLMClient(settings)
    except Exception as e:
        ui.show_error(f"Failed to load model: {e}")
        sys.exit(1)

    shell = get_shell_adapter()
    repl = GtermREPL(
        settings=settings,
        llm=llm,
        history=ConversationHistory(limit=settings.history_limit),
        shell=shell,
        ui=ui,
        prompt_builder=PromptBuilder(shell),
        hw_spec=hw,
    )
    repl.run()


@main.command("models")
def cmd_models() -> None:
    """List available models and download status."""
    ui = UIRenderer()
    hw = detect_hardware()
    recommended = recommend_model(hw)
    budget = hw.gpu_vram_gb if hw.has_metal and hw.gpu_vram_gb > 0 else hw.ram_gb * 0.6

    ui.show_info(f"Detected hardware: {hw}")
    ui.show_info(f"Recommended model: [bold]{recommended.name}[/]")
    ui.show_model_table(list_models(), hw_budget_gb=budget)


@main.command("download")
@click.argument("model_name", required=False)
def cmd_download(model_name: str | None) -> None:
    """Download a model (auto-selects best for your hardware if no name given)."""
    ui = UIRenderer()
    hw = detect_hardware()

    if model_name:
        variant = _find_model_by_name(model_name)
        if variant is None:
            ui.show_error(f"Unknown model: {model_name!r}. Run `gterm models` to see options.")
            sys.exit(1)
    else:
        variant = recommend_model(hw)
        ui.show_info(f"Detected hardware: {hw}")
        ui.show_info(f"Recommended: [bold]{variant.name}[/] ({variant.size_gb:.1f}GB)")

    if is_downloaded(variant):
        ui.show_success(f"{variant.name} already downloaded at {get_local_model_path(variant)}")
        return

    if not ui.confirm_download(variant.name, variant.size_gb):
        ui.show_cancelled()
        return

    try:
        token = Settings().hf_token
        path = download_model(variant, hf_token=token)
        ui.show_success(f"Downloaded to {path}")
    except Exception as e:
        ui.show_error(f"Download failed: {e}")
        sys.exit(1)


@main.command("use")
@click.argument("model_name")
def cmd_use(model_name: str) -> None:
    """Switch to a model by name or #number. Downloads it first if needed.

    Examples:\n
      gterm use 1\n
      gterm use "e4b q4"\n
      gterm use "31b q8"
    """
    ui = UIRenderer()

    # support selection by index number
    variant = _find_model_by_name(model_name)
    if variant is None:
        ui.show_error(f"No match for {model_name!r}. Run `gterm models` to see options.")
        sys.exit(1)

    if not is_downloaded(variant):
        ui.show_info(f"{variant.name} ({variant.quant}) is not downloaded yet.")
        if not ui.confirm_download(variant.name, variant.size_gb):
            ui.show_cancelled()
            return
        try:
            token = Settings().hf_token
            download_model(variant, hf_token=token)
        except Exception as e:
            ui.show_error(f"Download failed: {e}")
            sys.exit(1)

    path = get_local_model_path(variant)
    save_default_model(path)
    ui.show_success(f"Default model set to [bold]{variant.name} ({variant.quant})[/]")
    ui.show_info(f"Saved to ~/.config/gterm/config.toml — run `gterm` to start.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_model(explicit_path: Path | None, ui: UIRenderer, hw) -> Path | None:
    """
    Resolve which model file to use:
    1. Explicit --model flag
    2. GTERM_MODEL_PATH env var (picked up by Settings automatically)
    3. Auto-detect: find best downloaded model, or offer to download
    """
    if explicit_path:
        return explicit_path

    # Try env/config-file setting first (Settings will validate existence)
    try:
        s = Settings()
        if s.model_path:
            return s.model_path
    except Exception:
        pass

    # Auto-select from downloaded models
    models = list_models()
    downloaded = [m for m in models if is_downloaded(m)]

    if downloaded:
        recommended = recommend_model(hw)
        best = next((m for m in downloaded if m == recommended), downloaded[0])
        ui.show_info(f"Using downloaded model: [bold]{best.name}[/]")
        return get_local_model_path(best)

    # Nothing available — offer to download
    ui.show_info(f"Detected hardware: {hw}")
    recommended = recommend_model(hw)
    ui.show_info(f"No model found. Recommended: [bold]{recommended.name}[/] ({recommended.size_gb:.1f}GB)")

    if not ui.confirm_download(recommended.name, recommended.size_gb):
        ui.show_cancelled()
        return None

    try:
        path = download_model(recommended)
        ui.show_success(f"Downloaded to {path}")
        return path
    except Exception as e:
        ui.show_error(f"Download failed: {e}")
        return None


def _find_model_by_name(name: str) -> ModelVariant | None:
    models = list_models()
    # by index number (as shown in `gterm models` table)
    try:
        idx = int(name.lstrip("#")) - 1
        if 0 <= idx < len(models):
            return models[idx]
    except ValueError:
        pass
    # by fuzzy name/quant match — ALL terms must match
    terms = name.lower().split()
    for m in models:
        haystack = f"{m.name} {m.quant} {m.filename}".lower()
        if all(t in haystack for t in terms):
            return m
    return None
