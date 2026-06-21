from loaders.docx_loader import DocxLoader

class DocxExtractor:
    def __init__(self, file_path):
        self.loader = DocxLoader(file_path)

    def extract_text(self):
        """Extracts and returns text from the DOCX."""
        doc = self.loader.load()
        return "\n".join([paragraph.text for paragraph in doc.paragraphs]).strip()
