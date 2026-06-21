from PIL import Image

class ImageLoader:
    def __init__(self, file_path):
        self.file_path = file_path

    def load(self):
        """Loads and returns the PIL Image object."""
        return Image.open(self.file_path)
