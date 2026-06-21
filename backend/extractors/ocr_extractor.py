from extractors.gemini_ocr import extract_text_from_image

class OCRExtractor:
    def __init__(self, file_path):
        self.file_path = file_path

    def extract_text(self):
        """Extracts and returns text from a raw image file using Gemini OCR."""
        try:
            with open(self.file_path, "rb") as f:
                image_bytes = f.read()
            
            ext = self.file_path.split(".")[-1].lower()
            mime_type = "image/png" if ext == "png" else "image/jpeg"
            
            text = extract_text_from_image(image_bytes, mime_type=mime_type)
            return text if text else ""
        except Exception as e:
            print(f"Error extracting text from image: {e}")
            return ""
