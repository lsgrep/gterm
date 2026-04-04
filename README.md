# gterm

Natural language terminal powered by Gemma 4 via llama.cpp.

Type what you want to do — gterm translates it to shell commands, shows them for confirmation, then runs them.

## Install

```bash
# global install (recommended)
uv tool install gterm

# or with pip
pip install gterm
```

> **Note:** `llama-cpp-python` is compiled from source on install.
> On Apple Silicon, Metal is used automatically (where supported).

## Quickstart

```bash
gterm                        # auto-downloads best model for your hardware
gterm models                 # list all available models
gterm download "31b q4"      # download a specific variant
gterm use "e4b q8"           # switch default model
```

Inside the REPL:

```
[gterm] ~/code > show me all files larger than 100MB
[gterm] ~/code > /model        # switch model interactively
[gterm] ~/code > /help         # show all commands
```

## Requirements

- Python 3.11+
- macOS 13+ or Linux
- ~4GB+ free disk space for the smallest model

## Configuration

Set via environment variables or `~/.config/gterm/config.toml`:

```bash
export GTERM_MODEL_PATH=/path/to/custom.gguf
export GTERM_N_CTX=32768
export GTERM_N_GPU_LAYERS=-1
export GTERM_HF_TOKEN=hf_...   # for faster HuggingFace downloads
```
