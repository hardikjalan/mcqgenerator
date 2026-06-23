"""
pptx_extractor.py
=================
Extracts text from PPTX files. Iterates slides/shapes for text and calls
Gemini OCR for large presentation images.

Raises structured DocumentProcessingError subclasses on all failure paths.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loaders.pptx_loader import PptxLoader
from extractors.gemini_ocr import extract_text_from_image
from exceptions import DocumentProcessingError, TextExtractionError
from logger import get_logger

logger = get_logger(__name__)

MAX_IMAGES_PER_DOC = 5
DEBUG_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "debug_extraction.txt")


class PptxExtractor:
    """
    Extracts text from a PPTX file.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the PPTX file.

    Raises
    ------
    FileNotFoundError, FileSizeError, CorruptedFileError
        Raised by PptxLoader during validation / loading.
    TextExtractionError
        Raised if text extraction fails after the file is opened.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.loader = PptxLoader(file_path)
        self.images_processed = 0

    def extract_text(self) -> str:
        """
        Extract and return all text from the PPTX.

        Returns
        -------
        str
            Extracted text (may be empty if the presentation has no readable content).

        Raises
        ------
        DocumentProcessingError subclasses on failure.
        """
        logger.info("Starting PPTX extraction: %s", self.file_path)

        # PptxLoader raises structured exceptions on failure — let them propagate
        prs = self.loader.load()

        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_results = []

        try:
            slide_area = (
                prs.slide_width * prs.slide_height
                if prs.slide_width and prs.slide_height
                else 1
            )

            for slide_num, slide in enumerate(prs.slides, start=1):
                slide_text = []
                image_ocr_text = []

                for shape in slide.shapes:
                    try:
                        # 13 == MSO_SHAPE_TYPE.PICTURE
                        if getattr(shape, "shape_type", None) == 13 and hasattr(shape, "image"):
                            if self.images_processed >= MAX_IMAGES_PER_DOC:
                                continue

                            w_px, h_px = shape.image.size

                            if w_px < 300 and h_px < 300:
                                continue
                            aspect_ratio = max(w_px / h_px, h_px / w_px) if h_px > 0 and w_px > 0 else 0
                            if aspect_ratio > 8:
                                continue

                            total_images_found += 1

                            shape_area = getattr(shape, "width", 0) * getattr(shape, "height", 0)
                            area_ratio = shape_area / slide_area if slide_area else 0

                            if area_ratio > 0.75 or w_px >= 300 or h_px >= 300:
                                try:
                                    image_bytes = shape.image.blob
                                    mime_type = shape.image.content_type
                                    reason = (
                                        f"{area_ratio * 100:.0f}% slide area"
                                        if area_ratio > 0.75
                                        else f"{w_px}x{h_px}px"
                                    )

                                    ocr_text = extract_text_from_image(image_bytes, mime_type=mime_type)
                                    ocr_char_count = len(ocr_text) if ocr_text else 0
                                    self.images_processed += 1
                                    ocr_results.append((self.images_processed, ocr_char_count))

                                    logger.info(
                                        "[Slide %d Image %d OCR] %s → %d chars",
                                        slide_num, self.images_processed, reason, ocr_char_count,
                                    )

                                    if ocr_text:
                                        image_ocr_text.append(ocr_text)
                                except Exception as img_ex:
                                    logger.warning(
                                        "[Slide %d Image OCR] Failed — skipping: %s",
                                        slide_num, img_ex, exc_info=True,
                                    )

                        elif hasattr(shape, "text") and shape.text.strip():
                            slide_text.append(shape.text.strip())

                    except Exception as shape_ex:
                        logger.warning(
                            "[Slide %d] Error processing shape — skipping: %s",
                            slide_num, shape_ex, exc_info=True,
                        )

                if slide_text:
                    combined = "\n".join(slide_text)
                    total_text_chars += len(combined)
                    text_content.append(combined)
                if image_ocr_text:
                    text_content.append("\n".join(image_ocr_text))

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(
                "Unexpected error during PPTX text extraction: %s — %s", self.file_path, e, exc_info=True
            )
            raise TextExtractionError(
                message=f"Unexpected error extracting text from PPTX: {e}",
                user_message="An error occurred while reading the presentation. The file may be corrupted or contain unsupported content.",
            ) from e

        final_text = "\n\n".join(text_content).strip()

        # ── Structured logging ─────────────────────────────────────────────────
        logger.info("[PPTX Text Layer] %d chars", total_text_chars)
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
