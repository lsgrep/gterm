# gterm

Local natural-language terminal powered by Gemma 4 via `llama.cpp`.

Describe what you want in plain English. `gterm` turns that into shell commands, shows the exact command before execution, and keeps enough context to help with follow-up requests.

## What it does

- Runs fully local inference with Gemma 4 GGUF models
- Picks a model that fits your hardware and downloads it on first use
- Learns your projects and common directories from shell history, with explicit consent
- Suggests a corrected command automatically when a command fails
- Gives a short follow-up summary after non-trivial command output
- Hands off full-terminal tools like `codex`, `aider`, `vim`, and `lazygit` without breaking their UI

## Install

From PyPI:

```bash
uv tool install gterm
```

or:

```bash
pip install gterm
```

From source:

```bash
uv tool install git+https://github.com/lsgrep/gterm
```

`llama-cpp-python` builds from source during install. Gemma 4 models with the `gemma4` architecture are currently forced onto CPU on macOS because of an upstream Metal crash in `llama.cpp`.

Platform status: `gterm` is actively tested on macOS. Linux is expected to work, but it has not been validated nearly as thoroughly yet.

## Quickstart

```bash
gterm
```

On first run, `gterm`:

1. detects your hardware
2. picks the best matching Gemma 4 model
3. offers to download it if needed
4. asks whether it may read your shell history for project context

Useful commands:

```bash
gterm models            # list all bundled model variants
gterm download "26b q4" # download a specific model
gterm use "e4b q8"      # set a default model
```

Once initialized, you can say things like:

```text
❯ show me memory usage
❯ go to the gterm project
❯ open my overlay-web repo in codex
❯ explain that error
```

## REPL behavior

Example prompt:

```text
  ~/code/lsgrep/personal/gterm   main ●  gterm
❯ show me memory usage
```

The prompt shows:

- current directory
- git branch and dirty state
- whether you are ahead or behind the remote

For each request, the model responds in exactly one mode:

- Shell command: a fenced shell block that `gterm` previews, then either auto-runs if it is read-only or asks for confirmation if it changes state
- `# ANSWER:`: a direct answer when you ask to explain or summarize output
- `# CLARIFY:`: only when the request is genuinely ambiguous or destructive

Before state-changing execution, you get:

```text
  [y]es  [n]o  [e]dit
```

`e` opens the generated command in `$EDITOR` so you can modify it before running. Read-only inspection commands such as `ls`, `cat`, `git status`, and similar safe pipelines run immediately after the preview panel.

After execution:

- successful multi-line output gets a short automatic summary
- failed commands trigger an automatic repair attempt
- `cd` changes update the REPL working directory without spawning a subshell

## Built-in commands

| Command | Description |
|---|---|
| `/model` | Open the model picker |
| `/model <name>` | Switch to a model by fuzzy name match |
| `/models` | List available models with fit/download status |
| `/init` | Rebuild project and directory context from shell history |
| `/clear` | Clear conversation history |
| `/history` | Show recent conversation turns |
| `/cwd` | Print current directory |
| `/help` | Show command help |
| `exit` / `quit` / Ctrl-D | Quit |

The REPL also supports tab completion for built-ins and model names after `/model`.

## Project-aware navigation

If you allow shell-history access, `gterm` extracts:

- known projects
- frequent directories

That enables requests like:

```text
❯ go to the germ project
❯ open segue in codex
❯ start aider in my api repo
```

Nothing is uploaded anywhere. The derived context is stored locally in `~/.config/gterm/state.json`.

## Interactive tools

`gterm` can launch full-terminal programs directly instead of trying to capture their output. That includes:

- `claude`
- `aider`
- `codex`
- `gemini`
- `vim`
- `nvim`
- `nano`
- `emacs`
- `hx`
- `micro`
- `less`
- `htop`
- `btop`
- `lazygit`
- `tig`

Typical handoff:

```text
❯ open my overlay project in codex
→ cd /path/to/project
→ codex
```

## Models

`gterm` ships with a registry of Gemma 4 GGUF variants from Bartowski's Hugging Face repos and chooses the largest model that fits your machine.

Families currently included:

| Model | Notes | Smallest bundled quant |
|---|---|---|
| Gemma 4 31B | dense model | `IQ1_M` |
| Gemma 4 26B-A4B | MoE | `IQ2_XXS` |
| Gemma 4 E4B | MoE | `IQ2_M` |
| Gemma 4 E2B | MoE | `IQ2_M` |

Selection is based on available RAM or Metal-accessible memory. Downloaded models live under `~/.config/gterm/models/`.

## Configuration

Configuration can come from environment variables or `~/.config/gterm/config.toml`.

Examples:

```bash
export GTERM_MODEL_PATH=/path/to/custom.gguf
export GTERM_N_CTX=4096
export GTERM_N_GPU_LAYERS=-1
export GTERM_N_THREADS=10
export GTERM_N_BATCH=2048
export GTERM_TEMPERATURE=0.2
export GTERM_MAX_TOKENS=512
export GTERM_HISTORY_LIMIT=20
export GTERM_HF_TOKEN=hf_...
export GTERM_PARANOID_MODE=true
```

Example `config.toml`:

```toml
model_path = "/path/to/model.gguf"
n_ctx = 4096
temperature = 0.2
paranoid_mode = false
```

`paranoid_mode` adds a stricter confirmation path for dangerous commands.

## Context and privacy

Shell history is read only after explicit consent. `gterm` currently looks at standard shell history files such as `~/.zsh_history` and `~/.bash_history` to infer project paths and frequently used directories.

To revoke consent or reset the cached context:

```bash
echo '{"history_consent": false}' > ~/.config/gterm/state.json
```

or:

```bash
rm ~/.config/gterm/state.json
gterm
```

## Requirements

- Python 3.11+
- macOS
- Linux may work, but is currently much less tested
- enough free disk and RAM for your chosen model

## License

Apache 2.0. See [LICENSE](LICENSE).
