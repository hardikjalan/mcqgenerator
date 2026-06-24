"""
image_loader.py
===============
Loads image files (PNG, JPG, JPEG) using Pillow, with full input validation
and corrupted-image detection.

Validation failures raise structured exceptions; callers are responsible
for logging them at the appropriate level. This module only logs at DEBUG
for expected failures and ERROR for truly unexpected ones.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PIL import Image, UnidentifiedImageError
from exceptions import FileNotFoundError, FileSizeError, UnsupportedFileTypeError, CorruptedFileError
from logger import get_logger, is_debug_mode

logger = get_logger(__name__)

# File-size enforcement is handled exclusively by the cumulative cap in main.py.
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
# Maximum image resolution (width * height pixels)
MAX_RESOLUTION_PIXELS = 100_000_000  # 100 MP


class ImageLoader:
    """Validates and loads an image file, raising structured exceptions on failure."""

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
            raise UnsupportedFileTypeError(ext)

        # 3. Read file size (used by empty-file check below)
        size_bytes = os.path.getsize(self.file_path)

        # 4. Empty file check
        if size_bytes == 0:
            raise CorruptedFileError(self.file_path, "file is empty")

    def load(self) -> Image.Image:
        """
        Validate and open the image file.

        Returns
        -------
        PIL.Image.Image
            The opened Pillow image object. The caller is responsible for
            closing it when done.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        UnsupportedFileTypeError
            If the file extension is not in {png, jpg, jpeg}.
        CorruptedFileError
            If Pillow cannot identify or decode the image.
        """
        self._validate()
        logger.debug("[OCR] Loading image: %s", self.file_path)

        try:
            img = Image.open(self.file_path)
            # Verify forces Pillow to fully decode the image data, catching
            # truncated or corrupted files that open() alone would not catch.
            img.verify()
        except UnidentifiedImageError as e:
            logger.debug("[OCR] Pillow could not identify image format: %s", e)
            raise CorruptedFileError(self.file_path, "Pillow could not identify the image format") from e
        except Exception as e:
            logger.debug("[OCR] Pillow open/verify failed: %s", e)
            raise CorruptedFileError(self.file_path, str(e)) from e

        # Re-open after verify() because verify() leaves the file in an unusable state
        try:
            img = Image.open(self.file_path)
        except Exception as e:
            logger.error("[OCR] Image re-open after verify failed: %s", e, exc_info=is_debug_mode())
            raise CorruptedFileError(self.file_path, str(e)) from e

        # 5. Resolution limit check
        width, height = img.size
        total_pixels = width * height
        if total_pixels > MAX_RESOLUTION_PIXELS:
            img.close()
            raise FileSizeError(
                self.file_path,
                total_pixels / 1_000_000,
                MAX_RESOLUTION_PIXELS / 1_000_000,
            )

        logger.debug("[OCR] Image loaded — %dx%d px, mode=%s", width, height, img.mode)
        return img
