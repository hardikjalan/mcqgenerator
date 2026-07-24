"""
pdf_extractor.py
================
Extracts text from PDF files. Uses PyMuPDF for native text extraction and
falls back to Gemini OCR for scanned or image-heavy pages.

Raises structured DocumentProcessingError subclasses on all failure paths.
Internal errors are logged once here; callers must not re-log them.
"""

import os


import fitz  # PyMuPDF
from app.services.extraction.loaders.pdf_loader import PDFLoader
from app.services.extraction.extractors.gemini_ocr import extract_text_from_image
from app.core.exceptions import DocumentProcessingError, TextExtractionError
from app.core.logger import get_logger, is_debug_mode
from app.core.config import DEBUG_OUTPUT_PATH, MAX_IMAGES_PER_DOC

logger = get_logger(__name__)



class PDFExtractor:
    """
    Extracts text from a PDF file.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the PDF file.

    Raises
    ------
    FileNotFoundError, FileSizeError, CorruptedFileError
        Raised by PDFLoader during validation / loading.
    TextExtractionError
        Raised if text extraction fails after the file is opened.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.loader = PDFLoader(file_path)
        self.images_processed = 0

    def extract_text(self) -> str:
        """
        Extract and return all text from the PDF.

        Uses native text layer first; falls back to Gemini OCR for pages
        that are scanned or heavily image-based.

        Returns
        -------
        str
            Extracted text (may be empty if the document has no readable content).

        Raises
        ------
        DocumentProcessingError subclasses on failure.
        """
        fname = os.path.basename(self.file_path)
        logger.info("[PDF] Starting: %s", fname)

        # PDFLoader raises structured exceptions on failure — let them propagate.
        # Loader logs only at DEBUG level; no duplicate error here.
        doc = self.loader.load()

        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_chars = 0

        try:
            for page_num, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text().strip()
                except Exception as e:
                    logger.debug("[PDF] Page %d — get_text failed: %s", page_num, e)
                    page_text = ""

                page_area = page.rect.width * page.rect.height

                # ── Image analysis ────────────────────────────────────────────
                try:
                    image_info = page.get_image_info()
                except Exception as e:
                    logger.debug("[PDF] Page %d — get_image_info failed: %s", page_num, e)
                    image_info = []

                qualifying_images = []
                for img in image_info:
                    bbox = img.get("bbox", (0, 0, 0, 0))
                    width = bbox[2] - bbox[0]
                    height = bbox[3] - bbox[1]
                    if width < 300 and height < 300:
                        continue
                    aspect_ratio = max(width / height, height / width) if height > 0 and width > 0 else 0
                    if aspect_ratio > 8:
                        continue
                    qualifying_images.append({"width": width, "height": height, "area": width * height})

                total_image_area = sum(img["area"] for img in qualifying_images)

                is_scanned = (len(page_text) < 50 and len(qualifying_images) > 0)
                is_image_heavy = (total_image_area / page_area) > 0.75 if page_area > 0 else False

                if qualifying_images:
                    total_images_found += len(qualifying_images)

                # ── OCR path ──────────────────────────────────────────────────
                if (is_scanned or is_image_heavy) and self.images_processed < MAX_IMAGES_PER_DOC:
                    try:
                        pix = page.get_pixmap(dpi=150)
                        image_bytes = pix.tobytes("jpeg")
                        del pix

                        ocr_text = extract_text_from_image(image_bytes, mime_type="image/jpeg")
                        chars = len(ocr_text) if ocr_text else 0
                        self.images_processed += 1
                        ocr_chars += chars

                        reason = "scanned" if is_scanned else "image-heavy (>75%)"
                        logger.info("[PDF] Page %d OCR (%s) → %d chars", page_num, reason, chars)

                        if ocr_text:
                            text_content.append(ocr_text)
                    except Exception as e:
                        # OCR is best-effort — warn and continue without stack trace
                        logger.warning("[PDF] Page %d OCR failed — skipping: %s", page_num, e)
                else:
                    if page_text:
                        total_text_chars += len(page_text)
                        text_content.append(page_text)

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(
                "[PDF] Unexpected extraction error: %s", e,
                exc_info=is_debug_mode(),
            )
            raise TextExtractionError(
                message=f"Unexpected error extracting text from PDF: {e}",
                user_message="An error occurred while reading the PDF. The file may be password-protected or corrupted.",
            ) from e
        finally:
            try:
                doc.close()
            except Exception:
                pass

        final_text = "\n".join(text_content).strip()

        # ── Single-line summary ────────────────────────────────────────────────
        logger.info(
            "[PDF] Done — %s | %d text chars | %d image(s) found | %d OCR chars | %d total chars",
            fname, total_text_chars, total_images_found, ocr_chars, len(final_text),
        )

        # ── Debug file (written only in DEBUG mode) ────────────────────────────
        if is_debug_mode():
            try:
                with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
                    f.write(final_text)
                logger.debug("[PDF] Debug file saved: %s", os.path.abspath(DEBUG_OUTPUT_PATH))
            except OSError as e:
                logger.debug("[PDF] Could not write debug file: %s", e)

        return final_text
