"""
exceptions.py
=============
Custom exceptions for the ingestion layer.

Each exception carries a user-safe ``message`` that routes.py can surface
directly in the API response.  Internal diagnostics go in the optional
``detail`` field — log it, never send it.
"""


class IngestionError(Exception):
    """Base class for all ingestion errors."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class UnsupportedFileTypeError(IngestionError):
    """Raised when the file's format is not in the registry."""

    def __init__(self, file_name: str, detected: str | None = None) -> None:
        ext = f" (detected as {detected})" if detected else ""
        super().__init__(
            f"Unsupported file type: {file_name}{ext}. "
            "Supported formats: PDF, DOC, DOCX, PPT, PPTX.",
        )


class CorruptedFileError(IngestionError):
    """Raised when a file cannot be read despite having a supported extension."""

    def __init__(self, file_name: str, reason: str = "") -> None:
        hint = f" — {reason}" if reason else ""
        super().__init__(
            f"Could not read {file_name}{hint}. "
            "The file may be corrupted, password-protected, or saved in an "
            "unsupported variant.  Try re-saving it as PDF or DOCX.",
        )


class EmptyDocumentError(IngestionError):
    """Raised when a file parses successfully but yields zero text."""

    def __init__(self, file_name: str) -> None:
        super().__init__(
            f"{file_name} was read successfully but contained no extractable "
            "text.  If the content is in images, try exporting the file as a "
            "text-based PDF first.",
        )
