import pytesseract
from loaders.image_loader import ImageLoader

class OCRExtractor:
    def __init__(self, file_path):
        self.loader = ImageLoader(file_path)

    def extract_text(self):
        """Extracts and returns text from the Image using OCR."""
        image = self.loader.load()
        return pytesseract.image_to_string(image).strip()
