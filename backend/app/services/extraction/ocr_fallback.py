"""
ocr_fallback.py
===============
Scanned-page OCR for PDFs, which no LlamaIndex file reader covers.

``PyMuPDFReader`` returns the PDF's *text layer*. A scanned page has no text
layer, so the reader returns an empty Document for it and the document silently
extracts to nothing. This module re-opens such a PDF with PyMuPDF, picks the
pages worth rasterising, and sends those to Gemini OCR.

The page-selection heuristics moved here unchanged from the old
``pdf_extractor``: an image counts only if it is at least 300 px on one side
and is not a thin banner (aspect ratio ≤ 8); a page is OCR'd when it either has
almost no text alongside a qualifying image (scanned) or its qualifying images
cover more than 75 % of the page (image-heavy). ``MAX_IMAGES_PER_DOC`` caps the
number of Gemini calls so cost stays predictable.

OCR here is best-effort. A page that fails to rasterise or OCR is logged and
skipped — it never fails the whole document.
"""

import fitz  # PyMuPDF

from app.core.config import MAX_IMAGES_PER_DOC
from app.core.logger import get_logger
from app.services.extraction.extractors.gemini_ocr import extract_text_from_image

logger = get_logger(__name__)

# Below this many characters per page, a PDF's text layer is thin enough that
# it is worth paying for a rasterise-and-OCR pass. This is only a cheap gate to
# avoid re-opening every PDF; the per-page checks below make the real decision.
MIN_CHARS_PER_PAGE = 50

# Rasterisation resolution. 150 dpi is legible for Gemini without producing
# multi-megabyte JPEGs.
RENDER_DPI = 150

# An image smaller than this on both sides is a logo or a bullet graphic.
MIN_IMAGE_SIDE_PX = 300

# Anything longer than this ratio is a rule, banner, or divider, not content.
MAX_IMAGE_ASPECT_RATIO = 8

# Fraction of page area that qualifying images must cover for the page to count
# as image-heavy even when it does have some text.
IMAGE_HEAVY_AREA_RATIO = 0.75


def looks_scanned(text_chars: int, page_count: int) -> bool:
    """
    Return True if a PDF's text layer is thin enough to warrant an OCR pass.

    Parameters
    ----------
    text_chars : int
        Total characters the reader recovered across all pages.
    page_count : int
        Number of pages the reader produced Documents for.
    """
    if page_count <= 0:
        return False
    return text_chars < MIN_CHARS_PER_PAGE * page_count


def _qualifying_images(page: fitz.Page, page_num: int) -> list[float]:
    """Return the areas of images on this page that are worth OCR'ing."""
    try:
        image_info = page.get_image_info()
    except Exception as e:
        logger.debug("[OCR-PDF] Page %d — get_image_info failed: %s", page_num, e)
        return []

    areas = []
    for img in image_info:
        bbox = img.get("bbox", (0, 0, 0, 0))
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]

        if width < MIN_IMAGE_SIDE_PX and height < MIN_IMAGE_SIDE_PX:
            continue
        if width <= 0 or height <= 0:
            continue
        if max(width / height, height / width) > MAX_IMAGE_ASPECT_RATIO:
            continue

        areas.append(width * height)
    return areas


def ocr_scanned_pages(file_path: str) -> str:
    """
    Rasterise and OCR the scanned or image-heavy pages of a PDF.

    Returns the joined OCR text, or an empty string if nothing qualified or
    every attempt failed. Never raises — the caller already has whatever text
    the reader recovered, and losing OCR should not lose that too.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.warning("[OCR-PDF] Could not reopen for OCR — skipping: %s", e)
        return ""

    ocr_text: list[str] = []
    images_processed = 0

    try:
        for page_num, page in enumerate(doc, start=1):
            if images_processed >= MAX_IMAGES_PER_DOC:
                logger.info(
                    "[OCR-PDF] Hit MAX_IMAGES_PER_DOC (%d) — %d page(s) left unread",
                    MAX_IMAGES_PER_DOC, doc.page_count - page_num + 1,
                )
                break

            try:
                page_text = page.get_text().strip()
            except Exception as e:
                logger.debug("[OCR-PDF] Page %d — get_text failed: %s", page_num, e)
                page_text = ""

            areas = _qualifying_images(page, page_num)
            if not areas:
                continue

            page_area = page.rect.width * page.rect.height
            is_scanned = len(page_text) < MIN_CHARS_PER_PAGE
            is_image_heavy = (
                sum(areas) / page_area > IMAGE_HEAVY_AREA_RATIO if page_area > 0 else False
            )

            if not (is_scanned or is_image_heavy):
                continue

            try:
                pix = page.get_pixmap(dpi=RENDER_DPI)
                image_bytes = pix.tobytes("jpeg")
                del pix

                text = extract_text_from_image(image_bytes, mime_type="image/jpeg")
                images_processed += 1

                reason = "scanned" if is_scanned else "image-heavy (>75%)"
                logger.info(
                    "[OCR-PDF] Page %d OCR (%s) → %d chars",
                    page_num, reason, len(text) if text else 0,
                )

                if text:
                    ocr_text.append(text)
            except Exception as e:
                # Best-effort — one bad page must not sink the document.
                logger.warning("[OCR-PDF] Page %d OCR failed — skipping: %s", page_num, e)
    finally:
        try:
            doc.close()
        except Exception:
            pass

    return "\n".join(ocr_text).strip()
