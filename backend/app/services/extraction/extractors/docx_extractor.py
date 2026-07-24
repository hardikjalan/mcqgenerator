"""
docx_extractor.py
=================
Extracts text from DOCX files. Iterates paragraphs and, for large embedded
images, calls Gemini OCR.

Raises structured DocumentProcessingError subclasses on all failure paths.
Internal errors are logged once here; callers must not re-log them.
"""

import os


from app.services.extraction.loaders.docx_loader import DocxLoader
from app.services.extraction.extractors.gemini_ocr import extract_text_from_image
from app.core.exceptions import DocumentProcessingError, TextExtractionError
from app.core.logger import get_logger, is_debug_mode
from app.core.config import DEBUG_OUTPUT_PATH, MAX_IMAGES_PER_DOC

logger = get_logger(__name__)



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
        fname = os.path.basename(self.file_path)
        logger.info("[DOCX] Starting: %s", fname)

        # DocxLoader raises structured exceptions on failure — let them propagate.
        doc = self.loader.load()

        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_chars = 0

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
                                chars = len(ocr_text) if ocr_text else 0
                                self.images_processed += 1
                                ocr_chars += chars

                                logger.info(
                                    "[DOCX] Image %d OCR — %dx%dpx → %d chars",
                                    self.images_processed, int(w_px), int(h_px), chars,
                                )

                                if ocr_text:
                                    text_content.append(ocr_text)
                            except Exception as img_ex:
                                # OCR is best-effort — warn without stack trace
                                logger.warning("[DOCX] Image OCR failed — skipping: %s", img_ex)

            except DocumentProcessingError:
                raise
            except Exception as e:
                # Shape iteration is non-critical; warn and continue
                logger.warning("[DOCX] Could not iterate inline shapes — skipping images: %s", e)

        except DocumentProcessingError:
            raise
        except Exception as e:
            logger.error(
                "[DOCX] Unexpected extraction error: %s", e,
                exc_info=is_debug_mode(),
            )
            raise TextExtractionError(
                message=f"Unexpected error extracting text from DOCX: {e}",
                user_message="An error occurred while reading the document. The file may be corrupted or contain unsupported content.",
            ) from e

        final_text = "\n".join(text_content).strip()

        # ── Single-line summary ────────────────────────────────────────────────
        logger.info(
            "[DOCX] Done — %s | %d text chars | %d image(s) found | %d OCR chars | %d total chars",
            fname, total_text_chars, total_images_found, ocr_chars, len(final_text),
        )

        # ── Debug file (written only in DEBUG mode) ────────────────────────────
        if is_debug_mode():
            try:
                with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
                    f.write(final_text)
                logger.debug("[DOCX] Debug file saved: %s", os.path.abspath(DEBUG_OUTPUT_PATH))
            except OSError as e:
                logger.debug("[DOCX] Could not write debug file: %s", e)

        return final_text
