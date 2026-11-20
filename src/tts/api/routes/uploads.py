"""Plain-text upload endpoint (ARCHITECTURE.md section 9.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from tts.api.errors import AppError
from tts.api.schemas import UploadResponse

router = APIRouter(tags=["uploads"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ACCEPTED_TYPES_MESSAGE = "only plain-text .txt files are accepted"


def _content_type_allowed(content_type: str | None) -> bool:
    if content_type is None:
        return False
    normalized = content_type.lower()
    return normalized.startswith("text/") or normalized == "application/octet-stream"


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


@router.post("/uploads", response_model=UploadResponse, summary="Read a plain-text file")
def upload_file(file: Annotated[UploadFile, File(...)]) -> UploadResponse:
    """Decode an uploaded .txt file for review; generation is a separate step."""
    filename = file.filename or ""
    if not filename.lower().endswith(".txt") or not _content_type_allowed(file.content_type):
        raise AppError(
            "UNSUPPORTED_FILE_TYPE", 415, f"Unsupported file type; {ACCEPTED_TYPES_MESSAGE}."
        )

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("FILE_TOO_LARGE", 413, "The file is larger than the 2 MB limit.")

    try:
        text = _decode(data)
    except UnicodeDecodeError as error:
        raise AppError(
            "DECODE_FAILED",
            415,
            "The file could not be decoded as UTF-8 or UTF-16 text.",
        ) from error

    return UploadResponse(text=text, filename=filename, size_bytes=len(data))
