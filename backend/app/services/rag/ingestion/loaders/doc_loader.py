"""
doc_loader.py
=============
Loader for legacy Word documents (.doc — OLE2 binary format).

``python-docx`` only supports the modern XML-based ``.docx`` format.
This loader attempts to extract text from binary ``.doc`` files using
the following fallback strategies:

1. COM Automation (win32com) — A reliable, self-contained Python solution 
   (requires Microsoft Word to be installed on Windows).
2. Antiword — A robust system-level extractor fallback.

Limitations
-----------
- Formatting (bold, italic, tables) is lost — only raw text is extracted.
- Embedded images and OLE objects are skipped.
- Password-protected or encrypted files raise ``CorruptedFileError``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


@loader_for(SupportedFormat.DOC)
class DocLegacyLoader(BaseLoader):
    """
    Read a legacy .doc file using multiple fallback strategies.

    Text cleaning is handled centrally by ``BaseLoader.clean_and_validate()``.
    """

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        text, method = self._extract_text_with_fallbacks(file_path)

        doc = Document(text=text)
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "extraction_method": method,
                    "format_note": "Legacy .doc — formatting not preserved",
                },
            }
        )
        self._attach_metadata(doc, doc_meta)
        return self.clean_and_validate([doc], file_name=file_path.name)

    # ── Internal ──────────────────────────────────────────────────────────

    def _extract_text_with_fallbacks(self, file_path: Path) -> tuple[str, str]:
        """
        Attempt to extract text using available methods, falling back on failure.
        Returns a tuple of (extracted_text, method_name).
        """
        errors = []

        # 1. Try win32com (Reliable, Python-based on Windows, requires Word)
        try:
            return self._extract_via_com(file_path), "win32com"
        except Exception as e:
            errors.append(f"win32com failed: {e}")

        # 2. Try antiword (System-level fallback)
        try:
            return self._extract_via_antiword(file_path), "antiword"
        except Exception as e:
            errors.append(f"antiword failed: {e}")

        # If both methods failed, return a clear error indicating no supported extractor.
        raise CorruptedFileError(
            file_path.name,
            reason=(
                "No supported .doc extraction method was available or successful. "
                "Ensure Microsoft Word is installed (if on Windows) or 'antiword' is in your PATH. "
                f"Diagnostics: {'; '.join(errors)}"
            )
        )

    @staticmethod
    def _extract_via_com(file_path: Path) -> str:
        """Extract text using Word COM automation (Windows only, requires Word)."""
        try:
            import win32com.client
            import pythoncom
        except ImportError as exc:
            raise RuntimeError("pywin32 is not installed.") from exc

        # Initialize COM for the current thread
        pythoncom.CoInitialize()

        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False

            # Open file as read-only
            doc = word.Documents.Open(str(file_path), ReadOnly=True)
            text = doc.Content.Text
            return text
        finally:
            if doc is not None:
                try:
                    doc.Close(False)  # WdDoNotSaveChanges
                except Exception:
                    pass
            if word is not None:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    @staticmethod
    def _extract_via_antiword(file_path: Path) -> str:
        """Extract text using the antiword CLI tool."""
        try:
            result = subprocess.run(
                ["antiword", str(file_path)],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except FileNotFoundError as exc:
            raise RuntimeError("antiword is not installed or not in PATH.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"antiword returned {exc.returncode}: {exc.stderr.strip()}") from exc
