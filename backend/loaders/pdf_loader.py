"""
pdf_loader.py
=============
Loads a PDF file using PyMuPDF (fitz), with full input validation and
corrupted-file detection before the document is opened.

Validation failures raise structured exceptions; callers are responsible
for logging them at the appropriate level. This module only logs at DEBUG
for expected failures and ERROR for truly unexpected ones.
"""

import os
import sys
import zipfile

# Ensure backend root is importable when this module is used standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import fitz  # PyMuPDF
from exceptions import FileNotFoundError, CorruptedFileError
from logger import get_logger, is_debug_mode

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
            raise FileNotFoundError(self.file_path)

        # 2. Extension check
        ext = self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""
        if ext not in ALLOWED_EXTENSIONS:
            from exceptions import UnsupportedFileTypeError
            raise UnsupportedFileTypeError(ext)

        # 3. Read file size (used by empty-file check below)
        size_bytes = os.path.getsize(self.file_path)

        # 4. Empty file check
        if size_bytes == 0:
            raise CorruptedFileError(self.file_path, "file is empty")

        # 5. PDF magic bytes check (%PDF header)
        try:
            with open(self.file_path, "rb") as f:
                header = f.read(5)
            if not header.startswith(b"%PDF"):
                raise CorruptedFileError(self.file_path, "not a valid PDF file (missing %PDF header)")
        except CorruptedFileError:
            raise
        except OSError as e:
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
        logger.debug("[PDF] Loading: %s", self.file_path)

        try:
            doc = fitz.open(self.file_path)
        except fitz.FileDataError as e:
            logger.debug("[PDF] PyMuPDF parse error: %s", e)
            raise CorruptedFileError(self.file_path, "PyMuPDF could not parse the file") from e
        except Exception as e:
            # Truly unexpected — log with full trace
            logger.error("[PDF] Unexpected open error: %s", e, exc_info=is_debug_mode())
            raise CorruptedFileError(self.file_path, str(e)) from e

        if doc.page_count == 0:
            doc.close()
            raise CorruptedFileError(self.file_path, "PDF contains no pages")

        logger.debug("[PDF] Loaded — %d pages: %s", doc.page_count, self.file_path)
        return doc
