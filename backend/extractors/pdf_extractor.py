import os
import fitz  # PyMuPDF
from loaders.pdf_loader import PDFLoader
from extractors.gemini_ocr import extract_text_from_image

MAX_IMAGES_PER_DOC = 20
DEBUG_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "debug_extraction.txt")

class PDFExtractor:
    def __init__(self, file_path):
        self.loader = PDFLoader(file_path)
        self.images_processed = 0

    def extract_text(self):
        """Extracts and returns text from the PDF, using OCR for scanned or image-heavy pages."""
        doc = self.loader.load()
        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_results = []

        try:
            for page_num, page in enumerate(doc, start=1):
                page_text = page.get_text().strip()
                page_area = page.rect.width * page.rect.height

                # Check for images and calculate area
                image_info = page.get_image_info()
                qualifying_images = []

                for img in image_info:
                    bbox = img['bbox']
                    width = bbox[2] - bbox[0]
                    height = bbox[3] - bbox[1]

                    # Filter: ignore small images
                    if width < 200 and height < 200:
                        continue
                    # Filter: ignore extreme aspect ratios
                    aspect_ratio = max(width / height, height / width) if height > 0 and width > 0 else 0
                    if aspect_ratio > 8:
                        continue

                    qualifying_images.append({'width': width, 'height': height, 'area': width * height})

                total_image_area = sum(img['area'] for img in qualifying_images)
                has_large_image = any(img['width'] >= 1000 or img['height'] >= 1000 for img in qualifying_images)
                is_scanned = len(page_text) < 20
                is_image_heavy = (total_image_area / page_area) > 0.75 if page_area > 0 else False

                if qualifying_images:
                    total_images_found += len(qualifying_images)

                if (is_scanned or is_image_heavy or has_large_image) and self.images_processed < MAX_IMAGES_PER_DOC:
                    # Render page and OCR
                    pix = page.get_pixmap(dpi=150)
                    image_bytes = pix.tobytes("jpeg")
                    del pix  # release memory

                    ocr_text = extract_text_from_image(image_bytes, mime_type="image/jpeg")
                    ocr_char_count = len(ocr_text) if ocr_text else 0
                    self.images_processed += 1
                    ocr_results.append((self.images_processed, ocr_char_count))

                    reason = "scanned" if is_scanned else ("image-heavy (>75%)" if is_image_heavy else "large image")
                    print(f"  [Page {page_num} OCR] Reason: {reason} → {ocr_char_count} chars")

                    if ocr_text:
                        text_content.append(ocr_text)
                else:
                    if page_text:
                        total_text_chars += len(page_text)
                        text_content.append(page_text)
        finally:
            doc.close()

        final_text = "\n".join(text_content).strip()

        # ── Structured Logging ─────────────────────────────────────────────
        print(f"\n[PDF Text Layer] {total_text_chars} chars")
        print(f"[Images Found] {total_images_found}")
        for i, (num, chars) in enumerate(ocr_results, start=1):
            print(f"[OCR Image {i}] {chars} chars")
        print(f"[Final Combined Text] {len(final_text)} chars")

        # ── Debug File ─────────────────────────────────────────────────────
        with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"[Debug File Saved] {os.path.abspath(DEBUG_OUTPUT_PATH)}\n")

        return final_text
