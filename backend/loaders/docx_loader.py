"""
docx_loader.py
==============
Loads a DOCX file using python-docx, with full input validation and
corrupted-file detection (DOCX files are ZIP archives).
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import docx
from exceptions import FileNotFoundError, UnsupportedFileTypeError, CorruptedFileError
from logger import get_logger

logger = get_logger(__name__)

# File-size enforcement is handled exclusively by the cumulative cap in main.py.
ALLOWED_EXTENSIONS = {"docx"}


class DocxLoader:
    """Validates and loads a DOCX file, raising structured exceptions on failure."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def _validate(self) -> None:
        """Run all pre-load validation checks."""
        # 1. File existence
        if not os.path.exists(self.file_path):
            logger.error("DOCX file not found: %s", self.file_path)
            raise FileNotFoundError(self.file_path)

        # 2. Extension check
        ext = self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""
        if ext not in ALLOWED_EXTENSIONS:
            logger.error("Unsupported extension '%s' passed to DocxLoader: %s", ext, self.file_path)
            raise UnsupportedFileTypeError(ext)

        # 3. Read file size (used by empty-file check below)
        size_bytes = os.path.getsize(self.file_path)

        # 4. Empty file check
        if size_bytes == 0:
            logger.error("DOCX file is empty: %s", self.file_path)
            raise CorruptedFileError(self.file_path, "file is empty")

        # 5. ZIP integrity check (DOCX is a ZIP archive)
        if not zipfile.is_zipfile(self.file_path):
            logger.error("DOCX file is not a valid ZIP archive: %s", self.file_path)
            raise CorruptedFileError(self.file_path, "not a valid DOCX file (failed ZIP integrity check)")

    def load(self) -> docx.Document:
        """
        Validate and open the DOCX file.

        Returns
        -------
        docx.Document
            The opened python-docx document object.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        UnsupportedFileTypeError
            If the file extension is not .docx.
        CorruptedFileError
            If the file fails ZIP validation or python-docx cannot parse it.
        """
        self._validate()
        logger.info("Loading DOCX: %s", self.file_path)

        try:
            document = docx.Document(self.file_path)
        except Exception as e:
            logger.error("python-docx could not open DOCX: %s — %s", self.file_path, e, exc_info=True)
            raise CorruptedFileError(self.file_path, str(e)) from e

        logger.info("DOCX loaded successfully — %d paragraphs: %s", len(document.paragraphs), self.file_path)
        return document
