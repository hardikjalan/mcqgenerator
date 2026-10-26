"""Read legacy Word piece tables and PowerPoint text atoms without running macros."""
import struct
from pathlib import Path
import olefile
from llama_index.core.schema import Document
from app.services.rag.schemas import StandardDocumentMetadata, SupportedFormat
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


def word_text(word: bytes, table: bytes) -> str:
    if len(word) < 0x1AA or struct.unpack_from("<H", word)[0] != 0xA5EC:
        raise ValueError("Unsupported Word binary version; re-save as DOCX.")
    if struct.unpack_from("<H", word, 10)[0] & 0x0100:
        raise ValueError("Password-protected documents cannot be read.")
    offset, size = struct.unpack_from("<II", word, 0x1A2)
    clx = table[offset:offset + size]
    position = 0
    while position < len(clx) and clx[position] == 1:
        position += 3 + struct.unpack_from("<H", clx, position + 1)[0]
    if position >= len(clx) or clx[position] != 2:
        # Older non-complex Word files have one contiguous text range.
        low, high = struct.unpack_from("<II", word, 24)
        return word[low:high].decode("cp1252", errors="replace")
    length = struct.unpack_from("<I", clx, position + 1)[0]
    pieces = clx[position + 5:position + 5 + length]
    count = (len(pieces) - 4) // 12
    main_characters = struct.unpack_from("<I", word, 0x4C)[0]
    output = []
    for index in range(max(0, count)):
        start, end = struct.unpack_from("<II", pieces, index * 4)
        if main_characters and start >= main_characters:
            break
        end = min(end, main_characters) if main_characters else end
        encoded = struct.unpack_from("<I", pieces, (count + 1) * 4 + index * 8 + 2)[0]
        compressed = bool(encoded & 0x40000000)
        start_byte = (encoded & 0x3FFFFFFF) // (2 if compressed else 1)
        size_bytes = (end - start) * (1 if compressed else 2)
        output.append(word[start_byte:start_byte + size_bytes].decode("cp1252" if compressed else "utf-16le", errors="replace"))
    return "".join(output).replace("\r", "\n").replace("\x07", "\t")


def powerpoint_pages(stream: bytes) -> list[str]:
    pages: list[list[str]] = []
    current: list[str] = []
    def records(data: bytes, depth: int = 0):
        nonlocal current
        if depth > 32:
            raise ValueError("PowerPoint nesting limit exceeded.")
        offset = 0
        while offset + 8 <= len(data):
            version, record_type, length = struct.unpack_from("<HHI", data, offset)
            end = offset + 8 + length
            if end > len(data):
                break
            payload = data[offset + 8:end]
            if record_type == 1006:  # Slide container
                if current:
                    pages.append(current)
                current = []
            if record_type in (4000, 4008):
                text = payload.decode("utf-16le" if record_type == 4000 else "cp1252", errors="replace").strip("\x00\r\n ")
                if text:
                    current.append(text.replace("\r", "\n"))
            elif version & 0xF == 0xF:
                records(payload, depth + 1)
            offset = end
    records(stream)
    if current:
        pages.append(current)
    return ["\n\n".join(page) for page in pages]


class LegacyLoader(BaseLoader):
    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            with olefile.OleFileIO(file_path) as container:
                if metadata.file_type == SupportedFormat.DOC:
                    word = container.openstream("WordDocument").read()
                    name = "1Table" if struct.unpack_from("<H", word, 10)[0] & 0x0200 else "0Table"
                    pages = [word_text(word, container.openstream(name).read())]
                else:
                    pages = powerpoint_pages(container.openstream("PowerPoint Document").read())
            result = []
            for index, text in enumerate(pages, 1):
                document = Document(text=text)
                self._attach_metadata(document, metadata.model_copy(update={
                    "page_or_slide_num": index, "total_pages_or_slides": len(pages),
                }))
                result.append(document)
            return self.clean_and_validate(result, metadata.file_name)
        except Exception as exc:
            raise CorruptedFileError(metadata.file_name, "Legacy Office extraction failed; re-save as DOCX/PPTX if encrypted or unsupported.") from exc


loader_for(SupportedFormat.DOC)(LegacyLoader)
loader_for(SupportedFormat.PPT)(LegacyLoader)
