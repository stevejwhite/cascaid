from typing import Literal

ErrorCode = Literal[
    "model_unavailable",
    "context_overflow",
    "invalid_structured_output",
    "model_timeout",
    "resource_exhausted",
    "unsupported_capability",
    "invalid_request",
]


class ModelError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.retryable = code in {"model_unavailable", "model_timeout", "resource_exhausted"}


def normalize_error(error: Exception) -> ModelError:
    return (
        error
        if isinstance(error, ModelError)
        else ModelError("model_unavailable", "The model adapter failed")
    )
