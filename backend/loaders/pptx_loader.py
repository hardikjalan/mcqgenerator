"""
pptx_loader.py
==============
Loads a PPTX file using python-pptx, with full input validation and
corrupted-file detection (PPTX files are ZIP archives).
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pptx import Presentation
from pptx.exc import PackageNotFoundError
from exceptions import FileNotFoundError, UnsupportedFileTypeError, CorruptedFileError
from logger import get_logger

logger = get_logger(__name__)

# File-size enforcement is handled exclusively by the cumulative cap in main.py.
ALLOWED_EXTENSIONS = {"pptx", "ppt"}


class PptxLoader:
    """Validates and loads a PPTX file, raising structured exceptions on failure."""

    def __init__(self, file_path: str):
        self.file_path = file_path

    def _validate(self) -> None:
        """Run all pre-load validation checks."""
        # 1. File existence
        if not os.path.exists(self.file_path):
            logger.error("PPTX file not found: %s", self.file_path)
            raise FileNotFoundError(self.file_path)

        # 2. Extension check
        ext = self.file_path.rsplit(".", 1)[-1].lower() if "." in self.file_path else ""
        if ext not in ALLOWED_EXTENSIONS:
            logger.error("Unsupported extension '%s' passed to PptxLoader: %s", ext, self.file_path)
            raise UnsupportedFileTypeError(ext)

        # 3. Read file size (used by empty-file check below)
        size_bytes = os.path.getsize(self.file_path)

        # 4. Empty file check
        if size_bytes == 0:
            logger.error("PPTX file is empty: %s", self.file_path)
            raise CorruptedFileError(self.file_path, "file is empty")

        # 5. ZIP integrity check (PPTX is a ZIP archive)
        if not zipfile.is_zipfile(self.file_path):
            logger.error("PPTX file is not a valid ZIP archive: %s", self.file_path)
            raise CorruptedFileError(self.file_path, "not a valid PPTX file (failed ZIP integrity check)")

    def load(self) -> Presentation:
        """
        Validate and open the PPTX file.

        Returns
        -------
        pptx.Presentation
            The opened python-pptx presentation object.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        UnsupportedFileTypeError
            If the file extension is not .pptx/.ppt.
        CorruptedFileError
            If the file fails ZIP validation or python-pptx cannot parse it.
        """
        self._validate()
        logger.info("Loading PPTX: %s", self.file_path)

        try:
            prs = Presentation(self.file_path)
        except PackageNotFoundError as e:
            logger.error("python-pptx PackageNotFoundError for: %s — %s", self.file_path, e, exc_info=True)
            raise CorruptedFileError(self.file_path, "python-pptx could not find the package structure") from e
        except Exception as e:
            logger.error("python-pptx could not open PPTX: %s — %s", self.file_path, e, exc_info=True)
            raise CorruptedFileError(self.file_path, str(e)) from e

        slide_count = len(prs.slides)
        logger.info("PPTX loaded successfully — %d slides: %s", slide_count, self.file_path)
        return prs
