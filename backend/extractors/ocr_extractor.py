"""
ocr_extractor.py
================
Extracts text from raw image files (PNG, JPG, JPEG) using Gemini OCR.

Raises structured DocumentProcessingError subclasses on all failure paths.
Errors are logged once here at the point of first catch; callers do not
re-log them.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loaders.image_loader import ImageLoader
from extractors.gemini_ocr import extract_text_from_image
from exceptions import DocumentProcessingError, TextExtractionError, OCRError
from logger import get_logger, is_debug_mode

logger = get_logger(__name__)

DEBUG_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "debug_extraction.txt")

MIME_TYPE_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class OCRExtractor:
    """
    Extracts text from an image file using Gemini OCR.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the image file (PNG, JPG, JPEG).

    Raises
    ------
    FileNotFoundError, FileSizeError, UnsupportedFileTypeError, CorruptedFileError
        Raised by ImageLoader during validation / loading.
    TextExtractionError
        Raised if the file cannot be read after loading.
    OCRError
        Raised if Gemini OCR fails after all retries.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.loader = ImageLoader(file_path)

    def extract_text(self) -> str:
        """
        Validate the image and extract text via Gemini OCR.

        Returns
        -------
        str
            Extracted text, or an empty string if no text was found.

        Raises
        ------
        DocumentProcessingError subclasses on failure.
        """
        fname = os.path.basename(self.file_path)
        logger.info("[OCR] Starting: %s", fname)

        # ImageLoader raises structured exceptions on failure — let them propagate.
        # Errors are already described in the exception; no need to log again here.
        img = self.loader.load()
        img.close()  # Only needed for validation; read raw bytes separately

        ext = self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""
        mime_type = MIME_TYPE_MAP.get(ext, "image/jpeg")

        try:
            with open(self.file_path, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            logger.error("[OCR] Could not read image bytes: %s", e)
            raise TextExtractionError(
                message=f"Could not read image file: {e}",
                user_message="The image file could not be read. Please try uploading it again.",
            ) from e

        # gemini_ocr handles retries and logging internally — just let exceptions propagate
        try:
            text = extract_text_from_image(image_bytes, mime_type=mime_type)
        except DocumentProcessingError:
            # Already logged inside gemini_ocr — re-raise without duplicate logging
            raise
        except Exception as e:
            logger.error("[OCR] Unexpected failure for %s: %s", fname, e, exc_info=is_debug_mode())
            raise OCRError(detail=str(e)) from e

        result = text.strip() if text else ""
        logger.info("[OCR] Done — %d chars from %s", len(result), fname)

        # ── Debug file (written only in DEBUG mode) ────────────────────────────
        if is_debug_mode():
            try:
                with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
                    f.write(result)
                logger.debug("[OCR] Debug file saved: %s", os.path.abspath(DEBUG_OUTPUT_PATH))
            except OSError as e:
                logger.debug("[OCR] Could not write debug file: %s", e)

        return result
