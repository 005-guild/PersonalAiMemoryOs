"""Content field constraints shared by HTTP and Markdown input."""

from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, StringConstraints

MAX_TITLE_LENGTH = 500
MAX_BODY_LENGTH = 2_000_000
MAX_SUMMARY_LENGTH = 100_000
MAX_CATEGORY_LENGTH = 200
MAX_TERM_LENGTH = 100
MAX_TERM_COUNT = 100


def canonical_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise ValueError("Use a valid UUID identifier.") from None


Identifier = Annotated[str, AfterValidator(canonical_uuid)]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_LENGTH)
]
Label = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TERM_LENGTH)
]
