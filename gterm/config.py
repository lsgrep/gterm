from pathlib import Path
from typing import Any, Optional

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

GTERM_CONFIG_DIR = Path.home() / ".config" / "gterm"
GTERM_MODELS_DIR = GTERM_CONFIG_DIR / "models"
_CONFIG_FILE = GTERM_CONFIG_DIR / "config.toml"


class Settings(BaseSettings):
    model_path: Optional[Path] = None
    n_ctx: int = 32768
    n_gpu_layers: int = -1
    temperature: float = 0.2
    max_tokens: int = 512
    history_limit: int = 20
    paranoid_mode: bool = False
    hf_token: Optional[str] = None  # HuggingFace token for private/gated models

    model_config = SettingsConfigDict(env_prefix="GTERM_")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if _CONFIG_FILE.exists():
            from pydantic_settings import TomlConfigSettingsSource
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=_CONFIG_FILE))
        return tuple(sources)


def load_settings(**overrides: Any) -> Settings:
    return Settings(**{k: v for k, v in overrides.items() if v is not None})


def save_default_model(model_path: Path) -> None:
    """Persist model_path to ~/.config/gterm/config.toml as the default."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    GTERM_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, "rb") as f:
            existing = tomllib.load(f)

    existing["model_path"] = str(model_path)

    with open(_CONFIG_FILE, "w") as f:
        for key, value in existing.items():
            if isinstance(value, str):
                f.write(f'{key} = "{value}"\n')
            else:
                f.write(f"{key} = {value}\n")
