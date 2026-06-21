from pptx import Presentation

class PptxLoader:
    def __init__(self, file_path):
        self.file_path = file_path

    def load(self):
        """Loads and returns the PPTX presentation object."""
        return Presentation(self.file_path)
