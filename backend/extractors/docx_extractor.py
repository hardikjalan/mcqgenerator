import os
from loaders.docx_loader import DocxLoader
from extractors.gemini_ocr import extract_text_from_image

MAX_IMAGES_PER_DOC = 20
DEBUG_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "debug_extraction.txt")

class DocxExtractor:
    def __init__(self, file_path):
        self.loader = DocxLoader(file_path)
        self.images_processed = 0

    def extract_text(self):
        """Extracts and returns text from the DOCX, including smart OCR for large images."""
        doc = self.loader.load()
        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_results = []

        # Extract text from paragraphs
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if text:
                total_text_chars += len(text)
                text_content.append(text)

        # Extract and evaluate images
        try:
            from docx.enum.shape import WD_INLINE_SHAPE

            for shape in doc.inline_shapes:
                if self.images_processed >= MAX_IMAGES_PER_DOC:
                    break

                if shape.type == WD_INLINE_SHAPE.PICTURE:
                    # EMU to pixels: 1 pixel = 9525 EMU at 96 DPI
                    w_px = shape.width / 9525 if shape.width else 0
                    h_px = shape.height / 9525 if shape.height else 0

                    # Filter: ignore small images
                    if w_px < 200 and h_px < 200:
                        continue
                    # Filter: ignore extreme aspect ratios
                    aspect_ratio = max(w_px / h_px, h_px / w_px) if h_px > 0 and w_px > 0 else 0
                    if aspect_ratio > 8:
                        continue

                    total_images_found += 1

                    # Trigger OCR for large images
                    if w_px >= 1000 or h_px >= 1000:
                        try:
                            rId = shape._inline.graphic.graphicData.pic.blipFill.blip.embed
                            image_part = doc.part.related_parts[rId]
                            image_bytes = image_part.blob
                            mime_type = image_part.content_type

                            ocr_text = extract_text_from_image(image_bytes, mime_type=mime_type)
                            ocr_char_count = len(ocr_text) if ocr_text else 0
                            self.images_processed += 1
                            ocr_results.append((self.images_processed, ocr_char_count))

                            print(f"  [DOCX Image {self.images_processed} OCR] {int(w_px)}x{int(h_px)}px → {ocr_char_count} chars")

                            if ocr_text:
                                text_content.append(ocr_text)
                        except Exception as img_ex:
                            print(f"  [DOCX Image Error] {img_ex}")

        except Exception as e:
            print(f"  [DOCX Shape Error] {e}")

        final_text = "\n".join(text_content).strip()

        # ── Structured Logging ─────────────────────────────────────────────
        print(f"\n[DOCX Text Layer] {total_text_chars} chars")
        print(f"[Images Found] {total_images_found}")
        for i, (num, chars) in enumerate(ocr_results, start=1):
            print(f"[OCR Image {i}] {chars} chars")
        print(f"[Final Combined Text] {len(final_text)} chars")

        # ── Debug File ─────────────────────────────────────────────────────
        with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"[Debug File Saved] {os.path.abspath(DEBUG_OUTPUT_PATH)}\n")

        return final_text
