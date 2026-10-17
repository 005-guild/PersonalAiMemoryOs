"""Stable, non-sensitive failures at the retrieval boundary."""


class RagError(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)
