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

``repair_line_wraps`` is separate. It is not applied to every format — only
to those whose line breaks are a layout artifact rather than meaning. See its
docstring.
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


# ── Optional: line-wrap repair (PDF and other fixed-layout sources) ───────────

# A PDF stores where each line of text was *printed*, not where sentences
# begin and end. Extracting it therefore produces a newline every ~90
# characters, in the middle of sentences:
#
#   "...convert light energy\ninto chemical energy stored in glucose."
#
# Worse, a real paragraph break looks exactly the same — one newline — so the
# document's actual structure is gone. Left alone this wrecks chunking, since
# a sentence-aware splitter that trusts newlines cuts mid-sentence, and each
# chunk then starts or ends on half a thought.
#
# This is NOT applied to slides or Word documents, where a newline separates a
# bullet or a paragraph and genuinely means something.

# A line ending in sentence-final punctuation is a real ending. A closing
# quote or bracket may follow it.
_SENTENCE_END_RE = re.compile(r'[.!?:;][")\]\u2019\u201d]*$')

# A word split across lines: "photosyn-\nthesis". Joined without the hyphen.
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")

# A line starting a new block rather than continuing one: a bullet, a numbered
# item, or a heading-like line beginning with a capital after a full stop.
_NEW_BLOCK_RE = re.compile(r"^\s*([\u2022\u2023\u25e6\u2043\u2219*\-\u2013\u2014]|\(?\d+[.)]|[A-Z]\.)\s")


def repair_line_wraps(text: str) -> str:
    """Rejoin lines that a fixed layout broke in the middle of a sentence.

    A line is treated as continuing the previous one unless there is evidence
    otherwise: the previous line ended a sentence, the next line starts a
    bullet or numbered item, or either side is blank. Being conservative here
    matters — wrongly joining two paragraphs costs a little structure, but
    wrongly splitting a sentence costs a chunk boundary in the wrong place,
    which is what the whole exercise is trying to avoid.
    """
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)

    lines = text.split("\n")
    out: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not out or not stripped or not out[-1].strip():
            out.append(line)
            continue

        previous = out[-1].rstrip()

        if _SENTENCE_END_RE.search(previous) or _NEW_BLOCK_RE.match(line):
            out.append(line)
            continue

        # A short previous line is likely a heading or a table cell, not a
        # wrapped sentence — a wrapped line runs nearly the full column width.
        if len(previous) < 40:
            out.append(line)
            continue

        out[-1] = f"{previous} {stripped}"

    return "\n".join(out)
