from dataclasses import dataclass
from pathlib import Path

from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn  # noqa: F401

from gterm.config import GTERM_MODELS_DIR
from gterm.hardware import HardwareSpec

# ---------------------------------------------------------------------------
# Model registry — sourced from bartowski/google_gemma-4-*-GGUF on HuggingFace
#
# Models ordered largest → smallest so recommend_model() picks the best fit.
# Gemma 4 lineup:
#   31B    — dense 31B model
#   26B-A4B — MoE: 26B total params, 4B active per token (needs full 26B in RAM)
#   E4B    — MoE: ~8B total params, 4B active ("Effective 4B")
#   E2B    — MoE: ~5B total params, 2B active ("Effective 2B")
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelVariant:
    name: str
    repo_id: str
    filename: str
    size_gb: float       # actual file size from HuggingFace
    min_ram_gb: float    # safe lower bound (size + ~30% overhead)
    quant: str


def _v(name: str, repo: str, filename: str, size_gb: float, quant: str) -> ModelVariant:
    return ModelVariant(
        name=name,
        repo_id=repo,
        filename=filename,
        size_gb=size_gb,
        min_ram_gb=round(size_gb * 1.3),
        quant=quant,
    )


_31B = "bartowski/google_gemma-4-31B-it-GGUF"
_26B = "bartowski/google_gemma-4-26B-A4B-it-GGUF"
_E4B = "bartowski/google_gemma-4-E4B-it-GGUF"
_E2B = "bartowski/google_gemma-4-E2B-it-GGUF"

MODEL_REGISTRY: list[ModelVariant] = [
    # ── 31B dense ────────────────────────────────────────────────────────────
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-Q8_0.gguf",    30.38, "Q8_0"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-Q6_K.gguf",    24.89, "Q6_K"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-Q5_K_M.gguf",  21.05, "Q5_K_M"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-Q4_K_M.gguf",  18.26, "Q4_K_M"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-Q3_K_M.gguf",  14.83, "Q3_K_M"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-IQ3_M.gguf",   14.09, "IQ3_M"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-Q2_K.gguf",    11.77, "Q2_K"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-IQ2_M.gguf",   11.78, "IQ2_M"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-IQ2_XXS.gguf", 10.09, "IQ2_XXS"),
    _v("Gemma 4 31B", _31B, "google_gemma-4-31B-it-IQ1_M.gguf",    9.41, "IQ1_M"),
    # ── 26B-A4B MoE ──────────────────────────────────────────────────────────
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-Q8_0.gguf",    25.00, "Q8_0"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-Q6_K.gguf",    21.28, "Q6_K"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-Q5_K_M.gguf",  17.99, "Q5_K_M"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-Q4_K_M.gguf",  15.87, "Q4_K_M"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-Q3_K_M.gguf",  12.13, "Q3_K_M"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-IQ3_M.gguf",   12.37, "IQ3_M"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-Q2_K.gguf",    10.20, "Q2_K"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-IQ2_M.gguf",    9.97, "IQ2_M"),
    _v("Gemma 4 26B-A4B", _26B, "google_gemma-4-26B-A4B-it-IQ2_XXS.gguf",  8.99, "IQ2_XXS"),
    # ── E4B MoE (~8B total, 4B active) ───────────────────────────────────────
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-Q8_0.gguf",    7.48, "Q8_0"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-Q6_K.gguf",    5.90, "Q6_K"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-Q5_K_M.gguf",  5.42, "Q5_K_M"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-Q4_K_M.gguf",  5.03, "Q4_K_M"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-Q3_K_M.gguf",  4.56, "Q3_K_M"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-IQ3_M.gguf",   4.44, "IQ3_M"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-Q2_K.gguf",    4.15, "Q2_K"),
    _v("Gemma 4 E4B", _E4B, "google_gemma-4-E4B-it-IQ2_M.gguf",   3.69, "IQ2_M"),
    # ── E2B MoE (~5B total, 2B active) ───────────────────────────────────────
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-Q8_0.gguf",    4.63, "Q8_0"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-Q6_K.gguf",    3.63, "Q6_K"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-Q5_K_M.gguf",  3.41, "Q5_K_M"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-Q4_K_M.gguf",  3.23, "Q4_K_M"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-Q3_K_M.gguf",  3.00, "Q3_K_M"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-IQ3_M.gguf",   2.94, "IQ3_M"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-Q2_K.gguf",    2.81, "Q2_K"),
    _v("Gemma 4 E2B", _E2B, "google_gemma-4-E2B-it-IQ2_M.gguf",   2.44, "IQ2_M"),
]


def recommend_model(spec: HardwareSpec) -> ModelVariant:
    budget_gb = spec.gpu_vram_gb if (spec.has_metal and spec.gpu_vram_gb > 0) else spec.ram_gb * 0.6
    candidates = [m for m in MODEL_REGISTRY if m.size_gb <= budget_gb]
    return candidates[0] if candidates else MODEL_REGISTRY[-1]


def list_models() -> list[ModelVariant]:
    return list(MODEL_REGISTRY)


def get_local_model_path(variant: ModelVariant) -> Path:
    return GTERM_MODELS_DIR / variant.filename


def is_downloaded(variant: ModelVariant) -> bool:
    return get_local_model_path(variant).exists()


def download_model(variant: ModelVariant, hf_token: str | None = None) -> Path:
    import threading
    import time

    from huggingface_hub import hf_hub_download
    from huggingface_hub.utils import disable_progress_bars, enable_progress_bars

    dest_dir = GTERM_MODELS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / variant.filename

    if dest_path.exists():
        return dest_path

    total_bytes = int(variant.size_gb * 1024 ** 3)
    label = f"Downloading {variant.name} ({variant.quant})"

    result: dict = {}
    exc: list[Exception] = []

    def _run() -> None:
        try:
            result["path"] = hf_hub_download(
                repo_id=variant.repo_id,
                filename=variant.filename,
                local_dir=str(dest_dir),
                token=hf_token or None,
            )
        except Exception as e:
            exc.append(e)

    disable_progress_bars()
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    )

    with progress:
        task = progress.add_task(label, total=total_bytes)
        while thread.is_alive():
            progress.update(task, completed=_largest_file_bytes(dest_dir))
            time.sleep(0.5)
        progress.update(task, completed=total_bytes)

    enable_progress_bars()

    if exc:
        raise exc[0]

    return Path(result["path"])


def _largest_file_bytes(root: Path) -> int:
    """Return the size of the largest file under root (includes partial downloads)."""
    best = 0
    for p in root.rglob("*"):
        try:
            if p.is_file() and not p.suffix == ".lock":
                s = p.stat().st_size
                if s > best:
                    best = s
        except OSError:
            pass
    return best
