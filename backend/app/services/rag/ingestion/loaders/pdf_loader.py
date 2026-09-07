"""
pdf_loader.py
=============
Loader for PDF files (.pdf).

Text is read with LlamaIndex's ``PDFReader`` (which delegates to ``pypdf``),
one ``Document`` per page.

Scanned pages
-------------
A PDF is a container, not a text format: a scan is a page-sized image with no
text layer, and ``pypdf`` correctly returns nothing for it. That is the single
most common "the upload worked but found no text" complaint, and it used to
surface as ``EmptyDocumentError`` for the whole file even when only some pages
were scans.

So any page whose text layer is below ``OCR_TEXT_LAYER_THRESHOLD`` characters
is rendered to an image and sent to OCR — but only when a provider is
configured, and only up to ``MAX_OCR_PAGES_PER_DOC`` pages, because each one
is a paid vision call and a 300-page scanned book would otherwise issue 300 of
them from a single upload. A page that OCR cannot read is left empty rather
than failing the document; its neighbours may be fine.

The threshold is not zero. Scanners routinely stamp a page number or a header
into the text layer, so a page with four characters is still a scan.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document
from llama_index.readers.file import PDFReader

from app import config
from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError
from app.services.rag.ingestion import ocr as ocr_module
from app.services.rag.ingestion.ocr import OCRFailedError
from app.services.rag.processing.cleaning import layout_aware_cleaner


@loader_for(SupportedFormat.PDF)
class PDFLoader(BaseLoader):
    """Read a PDF and return one Document per page, OCRing scanned pages."""

    def __init__(self) -> None:
        # A PDF records where each line was printed, not where sentences end,
        # so this loader cleans with line-wrap repair on top of the standard
        # rules. Slides and Word documents deliberately do not — there a
        # newline separates a bullet or a paragraph and carries meaning.
        super().__init__(cleaner=layout_aware_cleaner())
        self._reader = PDFReader(return_full_document=False)

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            raw_docs: list[Document] = self._reader.load_data(file_path)
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"pypdf could not read this PDF: {exc}",
            ) from exc

        total_pages = len(raw_docs)
        scanned = [
            index for index, doc in enumerate(raw_docs)
            if len(doc.text.strip()) < config.OCR_TEXT_LAYER_THRESHOLD
        ]

        ocr_pages = self._ocr_pages(file_path, scanned) if scanned else {}

        result: list[Document] = []
        for index, doc in enumerate(raw_docs):
            page_num = index + 1
            custom: dict[str, object] = {"page_label": str(page_num)}

            recovered = ocr_pages.get(index)
            if recovered:
                doc.set_content(recovered)
                custom["extraction_method"] = "ocr"
            elif index in scanned:
                custom["extraction_method"] = "none"
                custom["note"] = "no text layer and OCR did not recover any text"

            page_meta = metadata.model_copy(
                update={
                    "page_or_slide_num": page_num,
                    "total_pages_or_slides": total_pages,
                    "custom_metadata": custom,
                }
            )
            self._attach_metadata(doc, page_meta)
            result.append(doc)

        return self.clean_and_validate(result, file_name=file_path.name)

    # ── Internal ──────────────────────────────────────────────────────────

    def _ocr_pages(self, file_path: Path, page_indexes: list[int]) -> dict[int, str]:
        """Render and OCR the given pages. Returns index → recovered text.

        Every failure mode here is non-fatal: no provider, no PyMuPDF, a
        render error or a provider error all mean "this page stays empty",
        never "this document is broken".
        """
        provider = ocr_module.get_provider()
        if provider is None:
            return {}

        try:
            import pymupdf
        except ImportError:
            print("[pdf] PyMuPDF not installed — scanned pages cannot be OCR'd")
            return {}

        budget = page_indexes[: config.MAX_OCR_PAGES_PER_DOC]
        if len(page_indexes) > len(budget):
            print(
                f"[pdf] {file_path.name}: {len(page_indexes)} pages need OCR, "
                f"processing the first {len(budget)}"
            )

        recovered: dict[int, str] = {}
        try:
            with pymupdf.open(file_path) as pdf:
                for index in budget:
                    if index >= pdf.page_count:
                        continue
                    try:
                        pixmap = pdf[index].get_pixmap(dpi=config.OCR_RENDER_DPI)
                        text = provider.extract_text(
                            pixmap.tobytes("png"),
                            mime_type="image/png",
                            file_name=f"{file_path.name} page {index + 1}",
                        )
                    except OCRFailedError as exc:
                        print(f"[pdf] {file_path.name} page {index + 1}: {exc.detail}")
                        continue
                    except Exception as exc:  # noqa: BLE001
                        print(f"[pdf] {file_path.name} page {index + 1}: {exc}")
                        continue

                    if text.strip():
                        recovered[index] = text
        except Exception as exc:  # noqa: BLE001
            print(f"[pdf] {file_path.name}: could not open for OCR — {exc}")

        return recovered
