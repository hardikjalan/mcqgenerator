"""
salvage.py
==========
Recovering text from legacy binary Office formats (.doc, .ppt).

Modern Office files are ZIP archives of XML and can be *parsed*. The pre-2007
binary formats cannot, at least not without implementing a large, undocumented
record specification. What is done instead is salvage: decode the stream and
keep the parts that look like human language.

The whole difficulty is telling text from noise. A binary stream decoded as
text produces enormous amounts of plausible-looking characters — record
headers, offsets and style tables all decode into *something*. Three filters
are applied together, and each one exists because the previous is not enough:

1. **Repertoire.** Only ASCII printable, Latin-1/Latin-Extended letters and
   common typographic punctuation count as readable. Widening this to "any
   printable character" fails badly: binary decoded as UTF-16 lands all over
   the Unicode plane, and those code points are letters too, so a permissive
   class happily matches long runs of Devanagari-looking mojibake.
2. **Run length.** Text comes in runs. Noise, once the repertoire is narrow,
   fragments into isolated characters that no longer meet the minimum.
3. **Letter ratio.** Record padding sometimes clears both tests on digits and
   punctuation alone. Real prose is mostly letters and spaces.

The cost of filter 1 is that non-Latin scripts are not recovered. That is a
deliberate trade: for these formats a wrong answer is worse than no answer,
because nothing downstream can distinguish salvaged garbage from real course
material, and the caller can always re-save the file as .docx or .pptx to get
a complete parse instead.
"""

from __future__ import annotations

import re

# A run of readable characters this long is text; anything shorter inside a
# binary stream is almost always coincidence.
MIN_RUN = 4

# Below this much salvaged text a file is treated as unreadable rather than
# passed downstream as questionable content.
MIN_SALVAGED_CHARS = 40

_READABLE_RUN_RE = re.compile(r"[\x20-\x7e -ɏ‐-›]{%d,}" % MIN_RUN)

_MIN_LETTER_RATIO = 0.5


def salvage_readable(raw: bytes) -> str:
    """Pull readable text out of a binary stream.

    Both common encodings are tried — UTF-16LE (used by newer binary Office
    files) and single-byte (used by older ones) — and whichever yields more
    readable text wins, since a stream is one or the other and the loser
    decodes to noise that the filters discard anyway.
    """
    candidates = (
        raw.decode("utf-16-le", errors="ignore"),
        raw.decode("latin-1", errors="ignore"),
    )

    best: list[str] = []
    for decoded in candidates:
        runs = [
            stripped
            for run in _READABLE_RUN_RE.findall(decoded)
            if looks_like_text(run) and (stripped := run.strip())
        ]
        if sum(len(r) for r in runs) > sum(len(r) for r in best):
            best = runs

    return "\n".join(best)


def looks_like_text(run: str) -> bool:
    """True when *run* is mostly letters and spaces rather than symbols."""
    if not run:
        return False
    wordish = sum(1 for ch in run if ch.isalpha() or ch.isspace())
    return wordish / len(run) >= _MIN_LETTER_RATIO


def is_substantial(text: str) -> bool:
    """True when enough was recovered to be worth passing downstream."""
    return len(text) >= MIN_SALVAGED_CHARS
