import fitz  # PyMuPDF

class PDFLoader:
    def __init__(self, file_path):
        self.file_path = file_path

    def load(self):
        """Loads and returns the PyMuPDF Document object."""
        return fitz.open(self.file_path)
