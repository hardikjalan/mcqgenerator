"""
cleaner.py
==========
Pipeline coordinators for text cleaning.

``TextCleaner``
    Applies cleaning rules in sequence to a raw string.

``DocumentCleaner``
    Wraps ``TextCleaner`` to clean LlamaIndex ``Document`` objects,
    mutating ``doc.text`` in place so that ``metadata``, ``doc_id``,
    and ``extra_info`` are trivially preserved by reference.
"""

from __future__ import annotations

from llama_index.core.schema import Document

from app.services.rag.processing.cleaning.rules import (
    normalize_line_endings,
    normalize_unicode,
    remove_control_characters,
    normalize_whitespace,
)


class TextCleaner:
    """Pipeline coordinator: applies all cleaning rules in order to a string.

    Rule order:
        normalize_line_endings → normalize_unicode →
        remove_control_characters → normalize_whitespace → strip()
    """

    _PIPELINE = (
        normalize_line_endings,
        normalize_unicode,
        remove_control_characters,
        normalize_whitespace,
    )

    def clean(self, text: str) -> str:
        """Run the full cleaning pipeline on *text* and return the result."""
        for rule in self._PIPELINE:
            text = rule(text)
        return text.strip()


class DocumentCleaner:
    """Cleans LlamaIndex ``Document`` objects via ``TextCleaner``.

    Mutates ``doc.text`` in place and returns the same object so that
    ``doc.metadata``, ``doc.doc_id``, and ``doc.extra_info`` are preserved
    by reference without needing reconstruction.
    """

    def __init__(self, text_cleaner: TextCleaner | None = None) -> None:
        self._text_cleaner = text_cleaner or TextCleaner()

    def clean_document(self, doc: Document) -> Document:
        """Clean a single Document's text in place.

        Uses ``set_content()`` instead of direct ``doc.text`` assignment
        because LlamaIndex's Pydantic-based ``Document`` model does not
        expose a setter for the ``text`` property.  ``set_content()``
        updates the underlying text resource while preserving
        ``metadata``, ``doc_id``, and ``extra_info`` on the same object.
        """
        doc.set_content(self._text_cleaner.clean(doc.text))
        return doc

    def clean_documents(self, docs: list[Document]) -> list[Document]:
        """Clean all Documents in the list.

        Does **not** filter or drop documents — emptiness handling is
        centralised in ``BaseLoader.clean_and_validate()``.
        """
        return [self.clean_document(doc) for doc in docs]
