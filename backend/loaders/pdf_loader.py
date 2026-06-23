"""
pdf_loader.py
=============
Loads a PDF file using PyMuPDF (fitz), with full input validation and
corrupted-file detection before the document is opened.
"""

import os
import sys
import zipfile

# Ensure backend root is importable when this module is used standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import fitz  # PyMuPDF
from exceptions import FileNotFoundError, CorruptedFileError
from logger import get_logger

logger = get_logger(__name__)

# File-size enforcement is handled exclusively by the cumulative cap in main.py.
ALLOWED_EXTENSIONS = {"pdf"}


class PDFLoader:
    """Validates and loads a PDF file, raising structured exceptions on failure."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def _validate(self) -> None:
        """Run all pre-load validation checks."""
        # 1. File existence
        if not os.path.exists(self.file_path):
            logger.error("PDF file not found: %s", self.file_path)
            raise FileNotFoundError(self.file_path)

        # 2. Extension check
        ext = self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""
        if ext not in ALLOWED_EXTENSIONS:
            from exceptions import UnsupportedFileTypeError
            logger.error("Unsupported extension '%s' passed to PDFLoader: %s", ext, self.file_path)
            raise UnsupportedFileTypeError(ext)

        # 3. Read file size (used by empty-file check below)
        size_bytes = os.path.getsize(self.file_path)

        # 4. Empty file check
        if size_bytes == 0:
            logger.error("PDF file is empty: %s", self.file_path)
            raise CorruptedFileError(self.file_path, "file is empty")

        # 5. PDF magic bytes check (%PDF header)
        try:
            with open(self.file_path, "rb") as f:
                header = f.read(5)
            if not header.startswith(b"%PDF"):
                logger.error("File does not have PDF magic bytes: %s", self.file_path)
                raise CorruptedFileError(self.file_path, "not a valid PDF file (missing %PDF header)")
        except CorruptedFileError:
            raise
        except OSError as e:
            logger.error("Could not read PDF file header: %s — %s", self.file_path, e)
            raise CorruptedFileError(self.file_path, str(e))

    def load(self) -> fitz.Document:
        """
        Validate and open the PDF file.

        Returns
        -------
        fitz.Document
            The opened PyMuPDF document object.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        CorruptedFileError
            If the file is empty, not a valid PDF, or cannot be opened by PyMuPDF.
        """
        self._validate()
        logger.info("Loading PDF: %s", self.file_path)

        try:
            doc = fitz.open(self.file_path)
        except fitz.FileDataError as e:
            logger.error("PyMuPDF could not open PDF (corrupted?): %s — %s", self.file_path, e, exc_info=True)
            raise CorruptedFileError(self.file_path, "PyMuPDF could not parse the file") from e
        except Exception as e:
            logger.error("Unexpected error opening PDF: %s — %s", self.file_path, e, exc_info=True)
            raise CorruptedFileError(self.file_path, str(e)) from e

        if doc.page_count == 0:
            doc.close()
            logger.warning("PDF has no pages: %s", self.file_path)
            raise CorruptedFileError(self.file_path, "PDF contains no pages")

        logger.info("PDF loaded successfully — %d pages: %s", doc.page_count, self.file_path)
        return doc
