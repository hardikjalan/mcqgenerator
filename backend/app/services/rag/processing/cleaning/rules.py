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
4. ``strip_page_number_footers``
5. ``normalize_whitespace``
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


# ── 4. Page-number footer stripping ──────────────────────────────────────────

# Matches isolated page-number lines such as "14", "Page 14", "Page 14 of 120",
# or "- 14 -".  Only matches lines that contain nothing but the page reference.
_PAGE_NUM_LINE_RE = re.compile(
    r"^\s*(?:(?:Page\s+)?\d+(?:\s+of\s+\d+)?|-\s*\d+\s*-)\s*$",
    re.IGNORECASE,
)


def _is_protected_line(line: str) -> bool:
    """Return True if *line* contains structure that must not be stripped.

    Protected content:
    - Markdown headings (``#``)
    - Markdown table rows (``|``)
    - Math delimiters (``$``, ``$$``)
    - Numbered list items (``1.``, ``2.``)
    """
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return True
    if "|" in stripped:
        return True
    if "$" in stripped:
        return True
    # Numbered list: digit(s) followed by a dot and at least one space + text.
    if re.match(r"\d+\.\s+\S", stripped):
        return True
    return False


def strip_page_number_footers(text: str) -> str:
    """Remove isolated page-number lines from the text body.

    These are redundant in the pipeline because the authoritative page
    number is already stored in ``doc.metadata["page_or_slide_num"]``.

    Lines containing headings (``#``), table cells (``|``), math
    delimiters (``$``), or numbered-list items are never touched.
    """
    lines = text.split("\n")
    cleaned: list[str] = []
    last_content = max((i for i, value in enumerate(lines) if value.strip()), default=-1)
    in_code = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            cleaned.append(line)
        elif in_code or line.startswith(("    ", "\t")) or _is_protected_line(line):
            cleaned.append(line)
        elif (_PAGE_NUM_LINE_RE.match(line)
              and (re.search(r"[A-Za-z-]", line) or index == last_content)):
            continue  # drop isolated page-number line
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


# ── 5. Whitespace normalization ──────────────────────────────────────────────

# Matches 2+ spaces/tabs that follow a non-whitespace character,
# so leading whitespace on each line is never matched.
_INTERIOR_MULTI_WS_RE = re.compile(r"(?<=\S)[ \t]{2,}")

# 3+ consecutive newlines → double newline.
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")


def normalize_whitespace(text: str) -> str:
    """Structure-aware whitespace normalization.

    * Runs of 2+ spaces/tabs that follow a non-whitespace character
      are collapsed to a single space — **except** on lines containing
      ``|`` (Markdown table rows), which are left as-is to preserve
      column alignment.
    * Leading whitespace on each line is left as-is.
    * Trailing whitespace per line is stripped.
    * 3+ consecutive newlines are collapsed to ``\\n\\n``.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        if "|" in line:
            # Preserve table row spacing exactly.
            lines.append(line.rstrip())
        else:
            lines.append(_INTERIOR_MULTI_WS_RE.sub(" ", line).rstrip())
    joined = "\n".join(lines)
    return _EXCESS_NEWLINES_RE.sub("\n\n", joined)


def repair_line_wrapping(text: str) -> str:
    """Join prose wraps and split-word hyphens while preserving structural blocks."""
    lines = text.split("\n")
    output: list[str] = []
    in_code = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_code = not in_code
        protected = in_code or not line.strip() or bool(re.match(r"\s*(?:[#|$*+•-]|\d+[.)]\s|```)", line)) or line.startswith(("    ", "\t"))
        previous = output[-1] if output else ""
        if not protected and re.search(r"[a-z]-$", previous) and re.match(r"[a-z]", line):
            output[-1] = previous[:-1] + line
        elif (not protected and previous and len(previous) >= 45
                and not re.match(r"\s*(?:[#|$*+•-]|\d+[.)]\s|```)", previous)
                and not previous.rstrip().endswith((".", "!", "?", ":", ";"))):
            output[-1] = previous.rstrip() + " " + line.lstrip()
        else:
            output.append(line)
    return "\n".join(output)
