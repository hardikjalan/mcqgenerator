from loaders.pptx_loader import PptxLoader

class PptxExtractor:
    def __init__(self, file_path):
        self.loader = PptxLoader(file_path)

    def extract_text(self):
        """Extracts and returns text from the PPTX."""
        prs = self.loader.load()
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text.strip()
