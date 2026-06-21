import docx

class DocxLoader:
    def __init__(self, file_path):
        self.file_path = file_path

    def load(self):
        """Loads and returns the DOCX document object."""
        return docx.Document(self.file_path)
