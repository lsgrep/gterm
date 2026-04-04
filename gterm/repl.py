import readline
from pathlib import Path

from gterm.config import Settings, save_default_model
from gterm.git_info import get_git_status
from gterm.context_state import set_consent, update_state
from gterm.executor import (
    confirm_and_run,
    extract_commands,
    is_answer_response,
    is_clarify_response,
    looks_like_direct_command,
    run_direct_commands,
)
from gterm.hardware import HardwareSpec
from gterm.history import ConversationHistory
from gterm.llm import LLMClient
from gterm.model_manager import download_model, get_local_model_path, is_downloaded, list_models
from gterm.platform_shell import ShellAdapter
from gterm.prompt import PromptBuilder
from gterm.ui import UIRenderer

HISTORY_FILE = Path.home() / ".gterm_history"
OUTPUT_CONTEXT_LIMIT = 2000
BUILTINS = {"/clear", "/history", "/cwd", "/models", "/model", "/init", "/help", "exit", "quit"}


class GtermREPL:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        history: ConversationHistory,
        shell: ShellAdapter,
        ui: UIRenderer,
        prompt_builder: PromptBuilder,
        hw_spec: HardwareSpec,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._history = history
        self._shell = shell
        self._ui = ui
        self._prompt_builder = prompt_builder
        self._hw_spec = hw_spec
        self._cwd = Path.cwd()

    def run(self) -> None:
        self._setup_readline()
        model_name = self._settings.model_path.name if self._settings.model_path else "unknown"
        self._ui.show_welcome(model_name, str(self._hw_spec), self._llm.metal_disabled)

        while True:
            try:
                git = get_git_status(self._cwd)
                print()
                self._ui.print_prompt_line(self._cwd, git)
                user_input = self._ui.prompt_input()
            except KeyboardInterrupt:
                # Ctrl+C at the prompt — clear the line and loop
                print()
                continue
            except EOFError:
                # Ctrl+D — clean exit
                print()
                self._ui.show_info("bye")
                break

            if not user_input:
                continue

            if not self._handle_input(user_input):
                break

    def _handle_input(self, user_input: str) -> bool:
        builtin_result = self._handle_builtin(user_input)
        if builtin_result is not None:
            return builtin_result

        if looks_like_direct_command(user_input, self._cwd):
            return self._run_direct_command(user_input)

        self._history.add_user(user_input)
        llm_response = self._query_llm()

        is_clarify, clarify_msg = is_clarify_response(llm_response)
        if is_clarify:
            self._ui.show_clarify(clarify_msg)
            self._history.set_last_assistant(f"# CLARIFY: {clarify_msg}")
            return True

        is_answer, answer_text = is_answer_response(llm_response)
        if is_answer:
            self._ui.show_answer(answer_text)
            self._history.set_last_assistant(f"# ANSWER: {answer_text}")
            return True

        commands = extract_commands(llm_response)
        if not commands:
            self._ui.show_error("Could not parse a command from the response.")
            self._history.set_last_assistant(llm_response)
            return True

        was_run, output, new_cwd, exit_code = confirm_and_run(
            commands,
            self._shell,
            self._ui,
            self._cwd,
            paranoid_mode=self._settings.paranoid_mode,
        )
        self._cwd = new_cwd

        context = f"Ran: `{'` && `'.join(commands)}`\n"
        if was_run and output:
            context += f"Output:\n{output[:OUTPUT_CONTEXT_LIMIT]}"
            if len(output) > OUTPUT_CONTEXT_LIMIT:
                context += "\n[output truncated]"
        elif not was_run:
            context += "User cancelled execution."

        self._history.set_last_assistant(context)

        if was_run and exit_code != 0:
            self._auto_recover(commands, output, exit_code)
        elif was_run and exit_code == 0 and output:
            self._auto_followup(output)

        return True

    def _run_direct_command(self, user_input: str) -> bool:
        self._ui.show_info("running direct command")
        self._history.add_user(user_input)
        was_run, output, new_cwd, exit_code = run_direct_commands(
            [user_input], self._shell, self._ui, self._cwd
        )
        self._cwd = new_cwd

        context = f"Ran directly: `{user_input}`\n"
        if was_run and output:
            context += f"Output:\n{output[:OUTPUT_CONTEXT_LIMIT]}"
            if len(output) > OUTPUT_CONTEXT_LIMIT:
                context += "\n[output truncated]"
        elif was_run:
            context += f"Exit code: {exit_code}"
        else:
            context += "Execution did not run."
        self._history.set_last_assistant(context)
        return True

    def _auto_followup(self, output: str) -> None:
        """After a successful command, show a brief insight if the output is non-trivial."""
        if output.count("\n") < 3:
            return  # skip for trivial single-line output

        system_prompt = self._prompt_builder.build(self._cwd)
        # Build messages with a synthetic analysis request — not saved to history
        messages = self._history.get_messages(system_prompt)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Briefly summarize the key findings from the output above in 1-2 sentences. "
                    "Respond with: # ANSWER: <your summary>"
                ),
            }
        )

        response = ""
        with self._ui.start_streaming() as live:
            for token in self._llm.stream_response(messages):
                response += token
                self._ui.update_stream(live, response)

        _, answer_text = is_answer_response(response)
        if answer_text:
            self._ui.show_followup(answer_text)

    def _auto_recover(self, failed_commands: list[str], error_output: str, exit_code: int) -> None:
        self._ui.show_info(f"Command failed (exit {exit_code}) — asking model to fix it…")
        recovery_prompt = (
            f"The command `{'` && `'.join(failed_commands)}` failed with exit code {exit_code}.\n"
            f"Error:\n{error_output[:OUTPUT_CONTEXT_LIMIT]}\n"
            "Respond with ONLY a corrected shell command in a fenced code block. "
            "Do not use # ANSWER or # CLARIFY."
        )
        self._history.add_user(recovery_prompt)
        recovery_response = self._query_llm()

        is_clarify, clarify_msg = is_clarify_response(recovery_response)
        if is_clarify:
            self._ui.show_clarify(clarify_msg)
            self._history.set_last_assistant(f"# CLARIFY: {clarify_msg}")
            return

        is_answer, answer_text = is_answer_response(recovery_response)
        if is_answer:
            self._ui.show_answer(answer_text)
            self._history.set_last_assistant(f"# ANSWER: {answer_text}")
            return

        fixed_commands = extract_commands(recovery_response)
        if not fixed_commands:
            self._history.set_last_assistant(recovery_response)
            return

        was_run, output, new_cwd, new_exit = confirm_and_run(
            fixed_commands,
            self._shell,
            self._ui,
            self._cwd,
            paranoid_mode=self._settings.paranoid_mode,
        )
        self._cwd = new_cwd

        context = f"Ran (recovery): `{'` && `'.join(fixed_commands)}`\n"
        if was_run and output:
            context += f"Output:\n{output[:OUTPUT_CONTEXT_LIMIT]}"
        elif not was_run:
            context += "User cancelled."
        self._history.set_last_assistant(context)

    def _handle_builtin(self, cmd: str) -> bool | None:
        lower = cmd.lower()
        if lower in ("exit", "quit"):
            self._ui.show_info("bye")
            return False
        if lower == "/clear":
            self._history.clear()
            self._ui.show_info("history cleared")
            return True
        if lower == "/history":
            self._ui.show_history(self._history.display_turns())
            return True
        if lower == "/cwd":
            self._ui.show_info(str(self._cwd))
            return True
        if lower == "/models":
            budget = (
                self._hw_spec.gpu_vram_gb
                if self._hw_spec.has_metal and self._hw_spec.gpu_vram_gb > 0
                else self._hw_spec.ram_gb * 0.6
            )
            self._ui.show_model_table(list_models(), self._settings.model_path, hw_budget_gb=budget)
            return True
        if lower == "/model" or lower.startswith("/model "):
            arg = cmd[len("/model") :].strip() or None
            self._switch_model(arg)
            return True
        if lower == "/init":
            self._reinit_context()
            return True
        if lower == "/help":
            self._ui.show_help()
            return True
        return None

    def _query_llm(self) -> str:
        system_prompt = self._prompt_builder.build(self._cwd)
        messages = self._history.get_messages(system_prompt)

        buffer = ""
        try:
            with self._ui.start_streaming() as live:
                for token in self._llm.stream_response(messages):
                    buffer += token
                    self._ui.update_stream(live, buffer)
        except KeyboardInterrupt:
            self._ui.show_info("interrupted")

        return buffer

    def _reinit_context(self) -> None:
        from gterm.context_state import load_state

        state = load_state()
        if state.history_consent is False:
            self._ui.show_info(
                "Shell history access is disabled. "
                "Set history_consent to true in ~/.config/gterm/state.json to enable."
            )
            return
        if state.history_consent is None:
            self._ui.console_print(
                "[dim]  Allow gterm to read shell history? \\[y]es / \\[n]o[/]  ", end=""
            )
            answer = input().strip().lower()
            granted = answer in ("y", "yes")
            set_consent(granted)
            if not granted:
                self._ui.show_info("Shell history access declined.")
                return

        try:
            ctx = update_state()
            self._prompt_builder.context = ctx
            self._ui.show_success(
                f"Context rebuilt: {len(ctx.projects)} project(s), "
                f"{len(ctx.recent_dirs)} frequent dir(s)."
            )
        except Exception as e:
            self._ui.show_error(f"Context rebuild failed: {e}")

    def _switch_model(self, name: str | None = None) -> None:
        models = list_models()
        budget = (
            self._hw_spec.gpu_vram_gb
            if self._hw_spec.has_metal and self._hw_spec.gpu_vram_gb > 0
            else self._hw_spec.ram_gb * 0.6
        )

        if name:
            terms = name.lower().split()
            variant = next(
                (m for m in models if all(t in f"{m.name} {m.quant}".lower() for t in terms)),
                None,
            )
            if variant is None:
                self._ui.show_error(f"No model matching {name!r}. Try /model for the picker.")
                return
        else:
            idx = self._ui.pick_model(models, self._settings.model_path, hw_budget_gb=budget)
            if idx is None:
                self._ui.show_cancelled()
                return
            variant = models[idx]

        if not is_downloaded(variant):
            self._ui.show_info(f"{variant.name} ({variant.quant}) is not downloaded.")
            if not self._ui.confirm_download(variant.name, variant.size_gb):
                self._ui.show_cancelled()
                return
            try:
                download_model(variant, hf_token=self._settings.hf_token)
            except Exception as e:
                self._ui.show_error(f"Download failed: {e}")
                return

        path = get_local_model_path(variant)
        try:
            with self._ui.start_status(f"loading {variant.name} ({variant.quant})..."):
                self._llm.reload(path)
        except Exception as e:
            self._ui.show_error(f"Failed to load model: {e}")
            return

        self._settings.model_path = path  # type: ignore[misc]
        self._history.clear()
        save_default_model(path)
        self._ui.show_success(
            f"Switched to [bold]{variant.name} ({variant.quant})[/] — history cleared."
        )

    def _setup_readline(self) -> None:
        try:
            readline.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass

        readline.set_history_length(1000)

        def completer(text: str, state: int) -> str | None:
            line = readline.get_line_buffer()
            options = self._complete(line, text)
            return options[state] if state < len(options) else None

        readline.set_completer(completer)
        readline.set_completer_delims(" \t")
        readline.parse_and_bind("tab: complete")

        import atexit

        atexit.register(readline.write_history_file, HISTORY_FILE)

    def _complete(self, line: str, text: str) -> list[str]:
        # completing the command itself
        if not line.startswith("/model ") and not line.startswith("/use "):
            return [b for b in BUILTINS if b.startswith(text)]

        # completing a model name after /model or /use
        fragment = text.lower()
        seen: set[str] = set()
        options: list[str] = []

        for m in list_models():
            # offer "Name Quant" style completions, e.g. "Gemma 4 31B Q8_0"
            candidate = f"{m.name} {m.quant}"
            key = candidate.lower()
            if key not in seen and fragment in key:
                seen.add(key)
                options.append(candidate)

        return options
