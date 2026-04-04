from dataclasses import dataclass, field


@dataclass
class ConversationHistory:
    limit: int = 20
    _turns: list[tuple[str, str]] = field(default_factory=list)  # (user, assistant) pairs

    def add_user(self, content: str) -> None:
        self._turns.append((content, ""))

    def set_last_assistant(self, content: str) -> None:
        if not self._turns:
            return
        user, _ = self._turns[-1]
        self._turns[-1] = (user, content)

    def get_messages(self, system_prompt: str) -> list[dict]:
        self._trim_to_limit()
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for user_msg, assistant_msg in self._turns:
            messages.append({"role": "user", "content": user_msg})
            if assistant_msg:
                messages.append({"role": "assistant", "content": assistant_msg})
        return messages

    def _trim_to_limit(self) -> None:
        while len(self._turns) > self.limit:
            self._turns.pop(0)

    def clear(self) -> None:
        self._turns.clear()

    def display_turns(self) -> list[tuple[str, str]]:
        return list(self._turns)
