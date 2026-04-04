import atexit
import gc
import os
import platform
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from llama_cpp import Llama

from gterm.config import Settings
from gterm.context_state import cache_model_arch, get_cached_arch


@contextmanager
def _silence_stderr() -> Iterator[None]:
    """Redirect C-level stderr to /dev/null for the duration of the block.

    verbose=False on Llama() suppresses Python-level logging but not all
    C-level messages (llama_context:, llama_kv_cache:, etc.) which write
    directly to fd 2. We dup/restore the fd to silence them.
    """
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    old_stderr_fd = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        sys.stderr.flush()
        os.dup2(old_stderr_fd, 2)
        os.close(old_stderr_fd)


# Gemma 4 MoE models currently crash on Metal during inference (upstream bug).
# Until fixed, force CPU for these architectures.
_METAL_BROKEN_ARCHS = {"gemma4"}


def _detect_arch(model_path: Path) -> str | None:
    """Read GGUF metadata to detect model architecture. Result is cached in state.json."""
    key = str(model_path)
    cached = get_cached_arch(key)
    if cached is not None:
        return cached
    try:
        with _silence_stderr():
            m = Llama(model_path=key, n_ctx=8, n_gpu_layers=0, verbose=False)
        arch = m.metadata.get("general.architecture")
        del m
        if arch:
            cache_model_arch(key, arch)
        return arch
    except Exception:
        return None


def _auto_threads() -> int:
    """Return the number of threads to use for inference.

    On Apple Silicon, restrict to performance cores only — efficiency cores
    add context-switching overhead that slows down compute-heavy workloads.
    """
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.perflevel0.physicalcpu"], text=True)
            return int(out.strip())
        except Exception:
            pass
    return os.cpu_count() or 4


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.model_path:
            raise ValueError("model_path is required")
        self._settings = settings
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._n_threads = settings.n_threads or _auto_threads()
        self._llm = self._load(settings.model_path)
        # Ensure Metal resources are freed before Python's C++ destructors run.
        # Without this, llama.cpp asserts on exit: GGML_ASSERT([rsets->data count] == 0)
        atexit.register(self._cleanup)

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
        with _silence_stderr():
            return Llama(
                model_path=str(model_path),
                n_ctx=self._settings.n_ctx,
                n_gpu_layers=gpu_layers,
                n_threads=self._n_threads,
                n_batch=self._settings.n_batch,
                flash_attn=True,  # helps both GPU and CPU paths
                verbose=False,
            )

    def _cleanup(self) -> None:
        """Explicitly free the model before Python's atexit/destructor phase."""
        self._llm = None
        gc.collect()

    def reload(self, model_path: Path) -> None:
        """Unload the current model and load a new one from model_path."""
        self._cleanup()
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
