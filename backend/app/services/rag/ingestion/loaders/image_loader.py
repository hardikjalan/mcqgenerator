from pathlib import Path
from io import BytesIO
from PIL import Image
from llama_index.core.schema import Document
from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.vision import read_image


@loader_for(SupportedFormat.IMAGE)
class ImageLoader(BaseLoader):
    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        with Image.open(file_path) as image:
            if image.width * image.height > 20_000_000:
                raise ValueError("Image exceeds the 20 megapixel OCR limit.")
            image.verify()
        with Image.open(file_path) as image:
            buffer = BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
        document = Document(text=read_image(buffer.getvalue(), "image/png"))
        self._attach_metadata(document, metadata.model_copy(update={
            "page_or_slide_num": 1, "total_pages_or_slides": 1,
            "custom_metadata": {"extraction_method": "vision_ocr"},
        }))
        return self.clean_and_validate([document], metadata.file_name)
