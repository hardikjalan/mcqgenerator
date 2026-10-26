"""Identify supported files by contents. Extensions never override a signature."""
from pathlib import Path
import zipfile
import olefile
from app.services.rag.schemas import SupportedFormat
from app.services.rag.ingestion.exceptions import UnsupportedFileTypeError

MAX_EXPANDED_BYTES = 100 * 1024 * 1024

class FileTypeDetector:
    @staticmethod
    def detect(file_path: Path) -> SupportedFormat:
        with file_path.open("rb") as stream:
            header = stream.read(16)
        if header.startswith(b"%PDF-"):
            return SupportedFormat.PDF
        if header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff"):
            return SupportedFormat.IMAGE
        if header.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(file_path) as archive:
                    if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_BYTES:
                        raise ValueError("Expanded Office document exceeds 100 MB.")
                    names = set(archive.namelist())
                    if "word/document.xml" in names:
                        return SupportedFormat.DOCX
                    if "ppt/presentation.xml" in names:
                        return SupportedFormat.PPTX
            except zipfile.BadZipFile:
                pass
        if header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            with olefile.OleFileIO(file_path) as archive:
                if archive.exists("WordDocument"):
                    return SupportedFormat.DOC
                if archive.exists("PowerPoint Document"):
                    return SupportedFormat.PPT
        raise UnsupportedFileTypeError(file_path.name, detected="unrecognised file signature")
