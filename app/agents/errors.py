"""Safe provider failures exposed without prompts, responses, or credentials."""


class AIError(Exception):
    """Only a stable error code and HTTP status may cross the API boundary."""

    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)
