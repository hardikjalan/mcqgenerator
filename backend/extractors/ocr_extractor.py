"""
ocr_extractor.py
================
Extracts text from raw image files (PNG, JPG, JPEG) using Gemini OCR.

Raises structured DocumentProcessingError subclasses on all failure paths.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loaders.image_loader import ImageLoader
from extractors.gemini_ocr import extract_text_from_image
from exceptions import DocumentProcessingError, TextExtractionError, OCRError
from logger import get_logger

logger = get_logger(__name__)

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
        Raised if Gemini OCR fails.
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
        logger.info("Starting OCR extraction: %s", self.file_path)

        # ImageLoader raises structured exceptions on failure — let them propagate
        img = self.loader.load()
        img.close()  # We only needed it for validation; read raw bytes separately

        ext = self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""
        mime_type = MIME_TYPE_MAP.get(ext, "image/jpeg")

        try:
            with open(self.file_path, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            logger.error("Failed to read image bytes: %s — %s", self.file_path, e, exc_info=True)
            raise TextExtractionError(
                message=f"Could not read image file: {e}",
                user_message="The image file could not be read. Please try uploading it again.",
            ) from e

        try:
            text = extract_text_from_image(image_bytes, mime_type=mime_type)
        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error("Gemini OCR failed for image: %s — %s", self.file_path, e, exc_info=True)
            raise OCRError(detail=str(e)) from e

        result = text.strip() if text else ""
        logger.info("[OCR Result] %d chars from: %s", len(result), self.file_path)
        return result
