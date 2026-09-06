"""
rules.py
========
Pure, format-agnostic text normalization functions.

Each function accepts a ``str`` and returns a ``str``.  They are applied
in the order listed below by ``TextCleaner`` — changing the order may
produce different results (e.g. line-ending normalization must happen
before any regex that relies on ``\\n`` only).

Functions
---------
1. ``normalize_line_endings``
2. ``normalize_unicode``
3. ``remove_control_characters``
4. ``normalize_whitespace``
"""

from __future__ import annotations

import re
import unicodedata


# ── 1. Line endings ──────────────────────────────────────────────────────────

def normalize_line_endings(text: str) -> str:
    """Unify ``\\r\\n`` and ``\\r`` into ``\\n``.

    Must run first so downstream rules only have to handle ``\\n``.
    """
    # Order matters: replace \r\n before bare \r.
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ── 2. Unicode normalization ─────────────────────────────────────────────────

# Zero-width / invisible characters to strip.
_INVISIBLE_CHARS = frozenset(
    "\u200b"  # zero-width space
    "\u200c"  # zero-width non-joiner
    "\u200d"  # zero-width joiner
    "\u200e"  # left-to-right mark
    "\u200f"  # right-to-left mark
    "\ufeff"  # byte-order mark / zero-width no-break space
)

# Characters to strip outright.
_STRIP_CHARS = _INVISIBLE_CHARS | {"\xad"}  # soft hyphen

# Non-breaking spaces → regular space.
_NBS_CHARS = {"\u00a0", "\u202f"}


def normalize_unicode(text: str) -> str:
    """NFKC normalization, strip invisible characters, convert non-breaking
    spaces to regular spaces, remove soft hyphens."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(
        {ord(ch): None for ch in _STRIP_CHARS}
        | {ord(ch): " " for ch in _NBS_CHARS}
    )
    return text


# ── 3. Control character removal ─────────────────────────────────────────────

# Matches non-printable control characters *except* \t (\x09) and \n (\x0a).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f-\x9f]")


def remove_control_characters(text: str) -> str:
    """Strip non-printable control characters.

    ``\\x0c`` (form feed) is replaced with ``\\n`` as a safe substitution
    to stop words merging across a form-feed split.
    All other control characters (except ``\\t`` and ``\\n``) are removed.
    """
    text = text.replace("\x0c", "\n")
    return _CONTROL_CHAR_RE.sub("", text)


# ── 4. Whitespace normalization ──────────────────────────────────────────────

# Matches 2+ spaces/tabs that follow a non-whitespace character,
# so leading whitespace on each line is never matched.
_INTERIOR_MULTI_WS_RE = re.compile(r"(?<=\S)[ \t]{2,}")

# 3+ consecutive newlines → double newline.
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")


def normalize_whitespace(text: str) -> str:
    """Basic whitespace normalization.

    * Runs of 2+ spaces/tabs that follow a non-whitespace character
      are collapsed to a single space.
    * Leading whitespace on each line is left as-is.
    * Trailing whitespace per line is stripped.
    * 3+ consecutive newlines are collapsed to ``\\n\\n``.
    """
    lines = [_INTERIOR_MULTI_WS_RE.sub(" ", line).rstrip()
             for line in text.split("\n")]
    joined = "\n".join(lines)
    return _EXCESS_NEWLINES_RE.sub("\n\n", joined)
