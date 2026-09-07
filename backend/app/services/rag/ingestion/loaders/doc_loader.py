"""
doc_loader.py
=============
Loader for legacy Word documents (.doc — OLE2 binary format).

``python-docx`` only supports the modern XML-based ``.docx`` format, so binary
``.doc`` files are read through three strategies in descending order of
fidelity:

1. **COM automation (win32com)** — drives a hidden Word instance. Exact, but
   needs Microsoft Word installed, so it is Windows-and-desktop only.
2. **antiword** — a system binary. Good output where it is installed.
3. **OLE2 salvage** — pure Python, no binaries, works everywhere. Lower
   fidelity, but it is the reason this format works in deployment at all:
   Railway and Render have neither Word nor antiword, so before this fallback
   existed every .doc upload succeeded locally and failed in production.

Which one ran is recorded in ``custom_metadata["extraction_method"]``, so a
support question about odd output can be answered without guessing.

Limitations
-----------
- Formatting (bold, italic, tables) is lost — only raw text is extracted.
- Embedded images and OLE objects are skipped.
- The salvage path does not recover non-Latin scripts (see ``salvage.py``).
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
from app.services.rag.ingestion.salvage import is_substantial, salvage_readable


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

        # 3. Salvage from the OLE2 stream. No external dependency, so this is
        #    the path that actually runs on a deployed host.
        try:
            return self._extract_via_salvage(file_path), "ole2_salvage"
        except CorruptedFileError:
            raise
        except Exception as e:
            errors.append(f"salvage failed: {e}")

        raise CorruptedFileError(
            file_path.name,
            reason=(
                "No .doc extraction method succeeded. "
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

    @staticmethod
    def _extract_via_salvage(file_path: Path) -> str:
        """Recover text from the OLE2 ``WordDocument`` stream.

        A .doc stores its text run-length encoded and interleaved with
        formatting tables, so this recovers the words but not their order-
        critical structure — headings and body text come back flat. Good
        enough to generate questions from; not good enough to reproduce the
        document.
        """
        try:
            import olefile
        except ImportError as exc:
            raise CorruptedFileError(
                file_path.name,
                reason="olefile is required for .doc support — pip install olefile",
            ) from exc

        try:
            ole = olefile.OleFileIO(str(file_path))
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"Not a valid OLE2 file: {exc}",
            ) from exc

        try:
            raw = None
            for stream_path in ole.listdir():
                if stream_path and stream_path[-1].lower() == "worddocument":
                    raw = ole.openstream(stream_path).read()
                    break
        finally:
            ole.close()

        if raw is None:
            raise CorruptedFileError(
                file_path.name,
                reason="No 'WordDocument' stream found",
            )

        text = salvage_readable(raw)

        if not is_substantial(text):
            raise CorruptedFileError(
                file_path.name,
                reason=(
                    "Only unreadable binary content could be recovered. Open it "
                    "in Word and save it as .docx, then upload that."
                ),
            )

        return text
