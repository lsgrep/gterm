from collections.abc import Generator
from pathlib import Path

from llama_cpp import Llama

from gterm.config import Settings

# Gemma 4 MoE models currently crash on Metal during inference (upstream bug).
# Until fixed, force CPU for these architectures.
_METAL_BROKEN_ARCHS = {"gemma4"}


def _detect_arch(model_path: Path) -> str | None:
    """Read GGUF metadata to detect model architecture without loading weights."""
    try:
        m = Llama(model_path=str(model_path), n_ctx=8, n_gpu_layers=0, verbose=False)
        arch = m.metadata.get("general.architecture")
        del m
        return arch
    except Exception:
        return None


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.model_path:
            raise ValueError("model_path is required")
        self._settings = settings
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._llm = self._load(settings.model_path)

    def _gpu_layers(self, model_path: Path) -> tuple[int, bool]:
        """Returns (n_gpu_layers, metal_forced_off)."""
        requested = self._settings.n_gpu_layers
        if requested == 0:
            return 0, False
        arch = _detect_arch(model_path)
        if arch in _METAL_BROKEN_ARCHS:
            return 0, True  # force CPU until upstream bug is fixed
        return requested, False

    @property
    def metal_disabled(self) -> bool:
        return self._metal_forced_off

    def _load(self, model_path: Path) -> Llama:
        gpu_layers, self._metal_forced_off = self._gpu_layers(model_path)
        return Llama(
            model_path=str(model_path),
            n_ctx=self._settings.n_ctx,
            n_gpu_layers=gpu_layers,
            flash_attn=(gpu_layers != 0),
            verbose=False,
        )

    def reload(self, model_path: Path) -> None:
        """Unload the current model and load a new one from model_path."""
        import gc
        self._llm = None   # drop reference first
        gc.collect()       # force C-level free before allocating next model
        self._llm = self._load(model_path)

    def stream_response(self, messages: list[dict]) -> Generator[str, None, None]:
        stream = self._llm.create_chat_completion(
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            token = delta.get("content", "")
            if token:
                yield token
