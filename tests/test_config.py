from pathlib import Path

from gterm import config


def test_load_settings_applies_defaults_and_ignores_none_overrides(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "_CONFIG_FILE", Path("/this/path/should/not/exist.toml"))
    settings = config.load_settings(model_path=None, n_ctx=None)

    assert settings.model_path is None
    assert settings.n_ctx == 4096
    assert settings.n_gpu_layers == -1
    assert settings.temperature == 0.2


def test_save_default_model_persists_model_path(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_file = config_dir / "config.toml"

    monkeypatch.setattr(config, "GTERM_CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "_CONFIG_FILE", config_file)

    model_path = tmp_path / "models" / "gemma.gguf"
    config.save_default_model(model_path)

    assert config_file.read_text() == f'model_path = "{model_path}"\n'
