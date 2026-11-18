"""Standard API error envelope.

Every non-2xx response uses the shape pinned in ARCHITECTURE.md section 9.1:

    {"error": {"code": "...", "message": "...", "details": {...} | null}}
"""

from __future__ import annotations

ERROR_STATUS: dict[str, int] = {
    "EMPTY_INPUT": 422,
    "INPUT_TOO_LONG": 422,
    "OUT_OF_RANGE": 422,
    # VOICE_NOT_FOUND is 422 in a request body and 404 when a stored
    # generation references a missing voice; callers pass 404 explicitly.
    "VOICE_NOT_FOUND": 422,
    "UNSUPPORTED_FILE_TYPE": 415,
    "FILE_TOO_LARGE": 413,
    "DECODE_FAILED": 415,
    "NO_VOICES_INSTALLED": 409,
    "GENERATION_NOT_FOUND": 404,
    "GENERATION_NOT_READY": 409,
    "GENERATION_BUSY": 409,
    "SUBTITLE_FORMAT_UNKNOWN": 400,
    "NOT_FOUND": 404,
    "ENGINE_ERROR": 500,
    "INTERNAL_ERROR": 500,
}


def error_envelope(
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the standard error envelope, always including the details key."""
    return {"error": {"code": code, "message": message, "details": details}}


class AppError(Exception):
    """Application error carrying one of the fixed section 9.1 codes."""

    code: str
    status: int
    message: str
    details: dict[str, object] | None

    def __init__(
        self,
        code: str,
        status: int,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        if code not in ERROR_STATUS:
            raise ValueError(f"Unknown API error code: {code!r}")
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.details = details

    def to_envelope(self) -> dict[str, object]:
        """Serialize this error exactly as section 9.1 requires."""
        return error_envelope(self.code, self.message, self.details)
