"""
test_salvage.py
===============
The filter that separates text from binary noise in legacy .doc and .ppt.

Before it existed, the .ppt loader decoded every OLE stream and kept anything
non-blank. Binary record headers decode into plausible-looking characters, so
the result was mojibake that passed the emptiness check and flowed downstream
as if it were course material.
"""

from __future__ import annotations

from app.services.rag.ingestion.salvage import (
    is_substantial,
    looks_like_text,
    salvage_readable,
)


def test_real_words_survive():
    stream = "Mendel's Laws of Inheritance".encode("utf-16-le")
    assert "Mendel's Laws of Inheritance" in salvage_readable(stream)


def test_binary_noise_does_not_survive():
    """The case the first version of this filter got wrong: a permissive
    character class matched long runs of exotic-script mojibake, because those
    code points are letters too."""
    assert salvage_readable(bytes(range(0, 32)) * 20) == ""


def test_text_is_recovered_from_between_binary_records():
    stream = (
        b"\x0f\x00\xe8\x03\x1a\x00\x00\x00"
        + "Punnett Squares".encode("utf-16-le")
        + b"\x00\x0f\xa8\x0f\x2c\x00\x00\x00"
        + "Allele segregation".encode("utf-16-le")
    )
    recovered = salvage_readable(stream)

    assert "Punnett Squares" in recovered
    assert "Allele segregation" in recovered


def test_single_byte_encoded_text_is_recovered():
    """Older files store text as single-byte characters; whichever decoding
    yields more readable text is the one used."""
    assert "Photosynthesis Overview" in salvage_readable(
        b"\x00\x01Photosynthesis Overview\x00\x02"
    )


def test_symbol_runs_are_not_text():
    """Record padding can clear the length test on punctuation alone."""
    assert looks_like_text("Ribosome function") is True
    assert looks_like_text("#$%^&*()_+{}|:<>?") is False


def test_substantiality_threshold():
    assert is_substantial("too short") is False
    assert is_substantial("Mitochondria generate ATP via oxidative phosphorylation.") is True
