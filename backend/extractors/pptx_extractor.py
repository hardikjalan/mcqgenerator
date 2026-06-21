import os
from loaders.pptx_loader import PptxLoader
from extractors.gemini_ocr import extract_text_from_image

MAX_IMAGES_PER_DOC = 20
DEBUG_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "debug_extraction.txt")

class PptxExtractor:
    def __init__(self, file_path):
        self.loader = PptxLoader(file_path)
        self.images_processed = 0

    def extract_text(self):
        """Extracts and returns text from the PPTX, using smart OCR for large images."""
        prs = self.loader.load()
        text_content = []
        total_text_chars = 0
        total_images_found = 0
        ocr_results = []

        slide_area = prs.slide_width * prs.slide_height if prs.slide_width and prs.slide_height else 1

        for slide_num, slide in enumerate(prs.slides, start=1):
            slide_text = []
            image_ocr_text = []

            for shape in slide.shapes:
                # 13 == MSO_SHAPE_TYPE.PICTURE
                if getattr(shape, "shape_type", None) == 13 and hasattr(shape, "image"):
                    if self.images_processed >= MAX_IMAGES_PER_DOC:
                        continue

                    w_px, h_px = shape.image.size

                    # Filter: ignore small images
                    if w_px < 200 and h_px < 200:
                        continue
                    # Filter: ignore extreme aspect ratios
                    aspect_ratio = max(w_px / h_px, h_px / w_px) if h_px > 0 and w_px > 0 else 0
                    if aspect_ratio > 8:
                        continue

                    total_images_found += 1

                    shape_area = getattr(shape, "width", 0) * getattr(shape, "height", 0)
                    area_ratio = shape_area / slide_area

                    if area_ratio > 0.75 or w_px >= 1000 or h_px >= 1000:
                        try:
                            image_bytes = shape.image.blob
                            mime_type = shape.image.content_type

                            reason = f"{area_ratio*100:.0f}% slide area" if area_ratio > 0.75 else f"{w_px}x{h_px}px"
                            ocr_text = extract_text_from_image(image_bytes, mime_type=mime_type)
                            ocr_char_count = len(ocr_text) if ocr_text else 0
                            self.images_processed += 1
                            ocr_results.append((self.images_processed, ocr_char_count))

                            print(f"  [Slide {slide_num} Image {self.images_processed} OCR] {reason} → {ocr_char_count} chars")

                            if ocr_text:
                                image_ocr_text.append(ocr_text)
                        except Exception as img_ex:
                            print(f"  [PPTX Image Error] Slide {slide_num}: {img_ex}")

                elif hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text.strip())

            if slide_text:
                combined = "\n".join(slide_text)
                total_text_chars += len(combined)
                text_content.append(combined)
            if image_ocr_text:
                text_content.append("\n".join(image_ocr_text))

        final_text = "\n\n".join(text_content).strip()

        # ── Structured Logging ─────────────────────────────────────────────
        print(f"\n[PPTX Text Layer] {total_text_chars} chars")
        print(f"[Images Found] {total_images_found}")
        for i, (num, chars) in enumerate(ocr_results, start=1):
            print(f"[OCR Image {i}] {chars} chars")
        print(f"[Final Combined Text] {len(final_text)} chars")

        # ── Debug File ─────────────────────────────────────────────────────
        with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"[Debug File Saved] {os.path.abspath(DEBUG_OUTPUT_PATH)}\n")

        return final_text
