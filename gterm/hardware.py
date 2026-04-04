import os
import platform
import subprocess
from dataclasses import dataclass


@dataclass
class HardwareSpec:
    ram_gb: float
    cpu_count: int
    is_apple_silicon: bool
    has_metal: bool
    gpu_vram_gb: float  # 0 if unknown or integrated

    def __str__(self) -> str:
        gpu_info = ""
        if self.is_apple_silicon:
            gpu_info = f", Apple Silicon (Metal, ~{self.gpu_vram_gb:.0f}GB unified)"
        elif self.has_metal:
            gpu_info = f", Metal GPU ({self.gpu_vram_gb:.0f}GB VRAM)"

        return (
            f"{self.ram_gb:.0f}GB RAM, "
            f"{self.cpu_count} CPU cores"
            f"{gpu_info}"
        )


def detect_hardware() -> HardwareSpec:
    ram_gb = _get_ram_gb()
    cpu_count = os.cpu_count() or 1
    is_apple_silicon = _is_apple_silicon()
    has_metal = _has_metal()
    gpu_vram_gb = _get_gpu_vram_gb(is_apple_silicon, ram_gb)

    return HardwareSpec(
        ram_gb=ram_gb,
        cpu_count=cpu_count,
        is_apple_silicon=is_apple_silicon,
        has_metal=has_metal,
        gpu_vram_gb=gpu_vram_gb,
    )


def _get_ram_gb() -> float:
    system = platform.system()
    if system == "Darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            return int(out.strip()) / (1024 ** 3)
        except Exception:
            pass
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 8.0  # safe fallback


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _has_metal() -> bool:
    if platform.system() != "Darwin":
        return False
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPDisplaysDataType"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return "Metal" in out
    except Exception:
        return _is_apple_silicon()


def _get_gpu_vram_gb(is_apple_silicon: bool, ram_gb: float) -> float:
    """
    On Apple Silicon, GPU shares unified memory.
    We estimate ~75% is accessible to GPU (macOS default Metal allocation).
    On discrete GPUs we try to parse system_profiler.
    """
    if is_apple_silicon:
        return round(ram_gb * 0.75, 1)

    if platform.system() == "Darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if "VRAM" in line and "MB" in line:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p in ("MB", "VRAM") and i > 0:
                            try:
                                mb = float(parts[i - 1].replace(",", ""))
                                return mb / 1024
                            except ValueError:
                                pass
        except Exception:
            pass

    return 0.0
