# gterm

Natural language terminal powered by Gemma 4 via llama.cpp.

Type what you want — gterm translates it to shell commands, shows them for confirmation, then runs them. When a command fails, it automatically suggests a fix.

## Install

```bash
# global install (recommended)
uv tool install gterm

# or with pip
pip install gterm
```

> **Note:** `llama-cpp-python` is compiled from source on install.
> Gemma 4 MoE models run on CPU only (Metal crash is an upstream llama.cpp bug — tracked in `_METAL_BROKEN_ARCHS`).

## Quickstart

```bash
gterm                        # auto-downloads best model for your hardware
gterm models                 # list all available models
gterm download "26b q4"      # download a specific variant
gterm use "e4b q8"           # switch default model
```

On first run, gterm asks for permission to read your shell history (`~/.zsh_history` / `~/.bash_history`) to learn your projects and frequent directories. This enables commands like:

```
❯ open my overlay-web project in codex
❯ go to the gterm project
❯ start aider on the segue repo
```

## The REPL

```
  ~/code/lsgrep/personal/gterm   main ●  gterm
❯ show me memory usage
```

The prompt shows your current directory, git branch, and dirty status. After each command, gterm automatically provides a brief insight on the output.

### Built-in commands

| Command | Description |
|---|---|
| `/model` | Switch model interactively (with tab completion) |
| `/models` | List all available models with download status |
| `/init` | Rebuild context from shell history |
| `/clear` | Clear conversation history |
| `/history` | Show conversation turns |
| `/cwd` | Print current directory |
| `/help` | Show this list |
| `exit` / Ctrl-D | Quit |

### Response modes

The model responds in one of three ways:

- **Shell command** — a fenced code block, shown as a proposed command for confirmation
- **`# ANSWER:`** — direct answer when you ask to explain or summarize output
- **`# CLARIFY:`** — only when a request is genuinely ambiguous or destructive

### Confirmation prompt

```
  [y]es  [n]o  [e]dit
```

Press `e` to open the proposed command in `$EDITOR` before running.

### Interactive tools

Commands that need a full terminal (editors, AI coding assistants) are handed off with TTY passthrough — no output capture:

```
❯ run codex in my overlay project   →  cd /path/to/overlay && codex
❯ open vim                          →  vim  (full terminal)
❯ start aider on main.py            →  aider main.py
```

Supported: `claude`, `aider`, `codex`, `gemini`, `vim`, `nvim`, `nano`, `lazygit`, `htop`, and more.

## Models

All Gemma 4 variants from [bartowski's GGUF repo](https://huggingface.co/bartowski) are included. gterm auto-selects the best fit for your hardware.

| Model | Params | Min RAM |
|---|---|---|
| Gemma 4 E2B | ~3B active | 3 GB |
| Gemma 4 E4B | ~5B active | 5 GB |
| Gemma 4 26B-A4B | ~4B active | 5 GB |
| Gemma 4 31B | 31B dense | 20 GB |

Each model is available in Q2_K through Q8_0 / BF16 quantizations.

## Configuration

Set via environment variables or `~/.config/gterm/config.toml`:

```bash
export GTERM_MODEL_PATH=/path/to/custom.gguf
export GTERM_N_CTX=4096          # context window (default: 4096)
export GTERM_N_GPU_LAYERS=-1     # GPU layers (-1 = all, 0 = CPU only)
export GTERM_N_THREADS=10        # inference threads (default: auto)
export GTERM_N_BATCH=2048        # prompt batch size (default: 2048)
export GTERM_TEMPERATURE=0.2
export GTERM_HF_TOKEN=hf_...     # for faster HuggingFace downloads
export GTERM_PARANOID_MODE=true  # extra confirmation for destructive commands
```

`~/.config/gterm/config.toml` example:

```toml
model_path = "/path/to/model.gguf"
n_ctx = 4096
temperature = 0.2
paranoid_mode = false
```

## Context & privacy

Shell history is read only with your explicit consent (asked once on first run). The extracted project list and frequent directories are stored in `~/.config/gterm/state.json`. Nothing leaves your machine — all inference runs locally.

To revoke consent or clear the state:

```bash
# disable history access
echo '{"history_consent": false}' > ~/.config/gterm/state.json

# or rebuild from scratch
rm ~/.config/gterm/state.json && gterm
```

## Requirements

- Python 3.11+
- macOS 13+ or Linux
- ~3GB+ free disk space for the smallest model
