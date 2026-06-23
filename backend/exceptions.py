"""
exceptions.py
=============
Custom exception hierarchy for the MCQ Generator document-processing pipeline.

All exceptions derive from DocumentProcessingError so callers can catch the
base class to handle any pipeline failure uniformly.
"""


class DocumentProcessingError(Exception):
    """
    Base exception for all pipeline errors.

    Attributes
    ----------
    message : str
        A developer-facing description of the error (logged internally).
    user_message : str
        A sanitized, frontend-safe message that is safe to return to the client.
    http_status : int
        The recommended HTTP status code for this kind of failure.
    """

    def __init__(
        self,
        message: str,
        user_message: str | None = None,
        http_status: int = 500,
    ):
        super().__init__(message)
        self.message = message
        self.user_message = user_message or "An unexpected error occurred while processing the document."
        self.http_status = http_status


# ── Validation Errors ─────────────────────────────────────────────────────────

class FileValidationError(DocumentProcessingError):
    """Raised when a file fails pre-processing validation (type, size, existence)."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(
            message=message,
            user_message=user_message or "The file could not be validated. Please check the file and try again.",
            http_status=400,
        )


class FileNotFoundError(FileValidationError):
    """Raised when the file does not exist at the given path."""

    def __init__(self, file_path: str):
        super().__init__(
            message=f"File not found: {file_path}",
            user_message="The file could not be found. It may have been deleted or the upload failed.",
        )


class UnsupportedFileTypeError(FileValidationError):
    """Raised when the file extension is not supported by any extractor."""

    def __init__(self, extension: str):
        super().__init__(
            message=f"Unsupported file type: .{extension}",
            user_message=f"The file type '.{extension}' is not supported. Supported types: PDF, DOCX, PPTX, PNG, JPG, JPEG.",
        )


class FileSizeError(FileValidationError):
    """Raised when the file exceeds the maximum allowed size."""

    def __init__(self, file_path: str, size_mb: float, max_mb: float):
        super().__init__(
            message=f"File too large: {file_path} is {size_mb:.1f} MB (max {max_mb:.1f} MB)",
            user_message=f"The file is too large ({size_mb:.1f} MB). Maximum allowed size is {max_mb:.1f} MB.",
        )


# ── Load Errors ───────────────────────────────────────────────────────────────

class FileLoadError(DocumentProcessingError):
    """Raised when a loader fails to open or parse the raw file."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(
            message=message,
            user_message=user_message or "The file could not be opened. It may be corrupted or in an unexpected format.",
            http_status=422,
        )


class CorruptedFileError(FileLoadError):
    """Raised when the file appears to be corrupted or is not a valid document."""

    def __init__(self, file_path: str, detail: str = ""):
        detail_suffix = f": {detail}" if detail else ""
        super().__init__(
            message=f"Corrupted or invalid file: {file_path}{detail_suffix}",
            user_message="The file appears to be corrupted or is not a valid document. Please try uploading it again.",
        )


# ── Extraction Errors ─────────────────────────────────────────────────────────

class TextExtractionError(DocumentProcessingError):
    """Raised when text extraction fails after the file has been successfully loaded."""

    def __init__(self, message: str, user_message: str | None = None):
        super().__init__(
            message=message,
            user_message=user_message or "Text could not be extracted from the document. Please try a different file.",
            http_status=422,
        )


class OCRError(TextExtractionError):
    """Raised when OCR (Gemini Vision) fails to process an image."""

    def __init__(self, detail: str = ""):
        detail_suffix = f": {detail}" if detail else ""
        super().__init__(
            message=f"OCR extraction failed{detail_suffix}",
            user_message="Image text extraction (OCR) failed. The image may be too low resolution or contain no readable text.",
        )
