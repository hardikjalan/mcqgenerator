"""
docx_extractor.py
=================
Extracts text from DOCX files. Iterates paragraphs and, for large embedded
images, calls Gemini OCR.

Raises structured DocumentProcessingError subclasses on all failure paths.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loaders.docx_loader import DocxLoader
from extractors.gemini_ocr import extract_text_from_image
from exceptions import DocumentProcessingError, TextExtractionError
from logger import get_logger

logger = get_logger(__name__)

MAX_IMAGES_PER_DOC = 5
DEBUG_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "debug_extraction.txt")


class DocxExtractor:
    """
    Extracts text from a DOCX file.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the DOCX file.

    Raises
    ------
    FileNotFoundError, FileSizeError, CorruptedFileError
        Raised by DocxLoader during validation / loading.
    TextExtractionError
        Raised if text extraction fails after the file is opened.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.loader = DocxLoader(file_path)
        self.images_processed = 0

    def extract_text(self) -> str:
        """
        Extract and return all text from the DOCX.

        Returns
        -------
        str
            Extracted text (may be empty if the document has no readable content).

        Raises
        ------
        DocumentProcessingError subclasses on failure.
        """
        logger.info("Starting DOCX extraction: %s", self.file_path)

        # DocxLoader raises structured exceptions on failure — let them propagate
        doc = self.loader.load()

        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_results = []

        try:
            # ── Paragraph text ─────────────────────────────────────────────────
            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if text:
                    total_text_chars += len(text)
                    text_content.append(text)

            # ── Embedded images (OCR) ──────────────────────────────────────────
            try:
                from docx.enum.shape import WD_INLINE_SHAPE

                for shape in doc.inline_shapes:
                    if self.images_processed >= MAX_IMAGES_PER_DOC:
                        break

                    if shape.type == WD_INLINE_SHAPE.PICTURE:
                        # EMU to pixels: 1 pixel = 9525 EMU at 96 DPI
                        w_px = shape.width / 9525 if shape.width else 0
                        h_px = shape.height / 9525 if shape.height else 0

                        if w_px < 300 and h_px < 300:
                            continue
                        aspect_ratio = max(w_px / h_px, h_px / w_px) if h_px > 0 and w_px > 0 else 0
                        if aspect_ratio > 8:
                            continue

                        total_images_found += 1

                        if w_px >= 300 or h_px >= 300:
                            try:
                                rId = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
                                image_part = doc.part.related_parts[rId]
                                image_bytes = image_part.blob
                                mime_type = image_part.content_type

                                ocr_text = extract_text_from_image(image_bytes, mime_type=mime_type)
                                ocr_char_count = len(ocr_text) if ocr_text else 0
                                self.images_processed += 1
                                ocr_results.append((self.images_processed, ocr_char_count))

                                logger.info(
                                    "[DOCX Image %d OCR] %dx%dpx → %d chars",
                                    self.images_processed, int(w_px), int(h_px), ocr_char_count,
                                )

                                if ocr_text:
                                    text_content.append(ocr_text)
                            except Exception as img_ex:
                                logger.warning(
                                    "[DOCX Image OCR] Failed for shape — skipping: %s", img_ex, exc_info=True
                                )

            except DocumentProcessingError:
                raise
            except Exception as e:
                logger.warning("[DOCX Shapes] Error iterating inline shapes — skipping images: %s", e, exc_info=True)

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error during DOCX text extraction: %s — %s", self.file_path, e, exc_info=True
            )
            raise TextExtractionError(
                message=f"Unexpected error extracting text from DOCX: {e}",
                user_message="An error occurred while reading the document. The file may be corrupted or contain unsupported content.",
            ) from e

        final_text = "\n".join(text_content).strip()

        # ── Structured logging ─────────────────────────────────────────────────
        logger.info("[DOCX Text Layer] %d chars", total_text_chars)
        logger.info("[Images Found] %d", total_images_found)
        for i, (_, chars) in enumerate(ocr_results, start=1):
            logger.info("[OCR Image %d] %d chars", i, chars)
        logger.info("[Final Combined Text] %d chars from: %s", len(final_text), self.file_path)

        # ── Debug file ─────────────────────────────────────────────────────────
        try:
            with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
                f.write(final_text)
            logger.debug("Debug file saved: %s", os.path.abspath(DEBUG_OUTPUT_PATH))
        except OSError as e:
            logger.warning("Could not write debug file: %s", e)

        return final_text
