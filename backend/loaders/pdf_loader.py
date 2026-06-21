from pypdf import PdfReader

class PDFLoader:
    def __init__(self, file_path):
        self.file_path = file_path

    def load(self):
        """Loads and returns the PDF document object."""
        return PdfReader(self.file_path)
