from loaders.pdf_loader import PDFLoader

class PDFExtractor:
    def __init__(self, file_path):
        self.loader = PDFLoader(file_path)

    def extract_text(self):
        """Extracts and returns text from the PDF."""
        reader = self.loader.load()
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
