"""
registry.py
===========
Maps ``SupportedFormat`` values to their ``BaseLoader`` instances.

New formats are added by calling ``register()`` — either directly or via
the ``@loader_for`` decorator.  Existing loaders are never touched.

Usage::

    from app.services.rag.ingestion.registry import loader_registry

    loader = loader_registry.get(SupportedFormat.PDF)
    docs   = loader.load(path, metadata)
"""

from __future__ import annotations

from app.services.rag.schemas import SupportedFormat
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.exceptions import UnsupportedFileTypeError


class LoaderRegistry:
    """Thread-safe registry of format → loader mappings."""

    def __init__(self) -> None:
        self._loaders: dict[SupportedFormat, BaseLoader] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def register(self, fmt: SupportedFormat, loader: BaseLoader) -> None:
        """Bind *fmt* to *loader*.  Overwrites any previous binding."""
        self._loaders[fmt] = loader

    def get(self, fmt: SupportedFormat) -> BaseLoader:
        """Return the loader for *fmt*, or raise ``UnsupportedFileTypeError``."""
        loader = self._loaders.get(fmt)
        if loader is None:
            raise UnsupportedFileTypeError(
                file_name=f"(format: {fmt.value})",
                detected=fmt.value,
            )
        return loader

    def has(self, fmt: SupportedFormat) -> bool:
        """Return True if a loader is registered for *fmt*."""
        return fmt in self._loaders

    @property
    def supported_formats(self) -> list[SupportedFormat]:
        """All formats with a registered loader."""
        return list(self._loaders.keys())


# ── Module-level singleton ────────────────────────────────────────────────────

loader_registry = LoaderRegistry()


# ── Decorator for convenient registration ─────────────────────────────────────

def loader_for(fmt: SupportedFormat):
    """
    Class decorator that instantiates a ``BaseLoader`` subclass and registers
    it for *fmt*::

        @loader_for(SupportedFormat.PDF)
        class PDFLoader(BaseLoader):
            ...
    """

    def decorator(cls: type[BaseLoader]) -> type[BaseLoader]:
        loader_registry.register(fmt, cls())
        return cls

    return decorator
