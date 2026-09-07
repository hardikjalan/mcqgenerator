"""
hierarchy.py
============
Deterministic hierarchy detection from Markdown / numbered headings.

Responsibilities:
- Parse Markdown heading lines (``#``, ``##``, ``###``, …) into relative
  hierarchy levels (Level 1, Level 2, Level 3, …).
- Assign ``chapter``, ``section``, ``subsection`` **only** when explicit
  numbering (``1.``, ``1.1``, ``1.1.1``) or text cues (``Chapter 3``)
  confirm them.
- Maintain cross-page continuity within a single document (``source_id``).
- Never aggressively guess hierarchy for ambiguous headings.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field

from app.services.rag.chunking.models import HierarchyContext


# ── Compiled patterns ────────────────────────────────────────────────────────

# Matches a Markdown heading line:  ``# Heading text``
# Group 1 = the ``#`` characters;  Group 2 = the heading title.
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

# ── Numbered heading patterns (applied to heading title text) ────────────────

# Chapter-level:  ``1.``, ``1``, ``Chapter 1``, ``Chapter 1: Title``
_CHAPTER_NUM_RE = re.compile(
    r"^(?:Chapter\s+)?(\d+)\.?\s",
    re.IGNORECASE,
)

# Section-level:  ``1.1``, ``1.1.``, ``Section 1.1``
_SECTION_NUM_RE = re.compile(
    r"^(?:Section\s+)?(\d+\.\d+)\.?\s",
    re.IGNORECASE,
)

# Subsection-level:  ``1.1.1``, ``Subsection 1.1.1``
_SUBSECTION_NUM_RE = re.compile(
    r"^(?:Subsection\s+)?(\d+\.\d+\.\d+)\.?\s",
    re.IGNORECASE,
)

# Explicit ``Chapter N`` keyword (regardless of level)
_CHAPTER_KEYWORD_RE = re.compile(r"^Chapter\s+\d+", re.IGNORECASE)

# Explicit ``Section N.M`` keyword (regardless of level)
_SECTION_KEYWORD_RE = re.compile(r"^Section\s+\d+\.\d+", re.IGNORECASE)


# ── Heading node (intermediate parse result) ─────────────────────────────────

@dataclass
class HeadingNode:
    """A single heading parsed from the document text."""

    level: int  # 1-based relative depth
    title: str  # heading text (without ``#`` prefix)
    line_index: int  # 0-based line offset within the page/document text


# ── Hierarchy tracker (stateful, cross-page) ─────────────────────────────────

@dataclass
class HierarchyTracker:
    """Maintains a running hierarchy state across pages of a single document.

    Call ``update()`` for every heading encountered to build the
    ``HierarchyContext``.  The tracker preserves the active heading path
    so continuation text on subsequent pages inherits its hierarchy.
    """

    # Active heading titles at each level.
    # Index 0 = Level 1, Index 1 = Level 2, …
    _levels: list[str] = field(default_factory=list)

    # Resolved chapter / section / subsection labels.
    _chapter: str | None = None
    _section: str | None = None
    _subsection: str | None = None

    def reset(self) -> None:
        """Clear all state — call when switching to a different document."""
        self._levels.clear()
        self._chapter = None
        self._section = None
        self._subsection = None

    def update(self, heading: HeadingNode) -> HierarchyContext:
        """Register a new heading and return the updated context snapshot."""
        level = heading.level
        title = heading.title.strip()

        # Ensure the levels list is long enough.
        while len(self._levels) < level:
            self._levels.append("")

        # Set the current level and clear deeper levels.
        self._levels[level - 1] = title
        self._levels = self._levels[:level]

        # Attempt to assign chapter / section / subsection from numbering
        # or keyword cues in the heading title.
        self._classify_heading(level, title)

        return self.current_context()

    def current_context(self) -> HierarchyContext:
        """Return a snapshot of the current hierarchy state."""
        path = [t for t in self._levels if t]
        heading = path[-1] if path else None
        # Find the deepest non-empty level.
        deepest_level = 0
        for i in range(len(self._levels) - 1, -1, -1):
            if self._levels[i]:
                deepest_level = i + 1
                break

        return HierarchyContext(
            level=deepest_level,
            heading=heading,
            chapter=self._chapter,
            section=self._section,
            subsection=self._subsection,
            path=list(path),
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _classify_heading(self, level: int, title: str) -> None:
        """Try to assign chapter/section/subsection based on explicit cues."""
        # Subsection check (most specific first).
        if _SUBSECTION_NUM_RE.match(title):
            self._subsection = title
            return

        # Section check.
        if _SECTION_NUM_RE.match(title):
            self._section = title
            self._subsection = None  # entering a new section clears subsection
            return

        # Chapter check (numbered or keyword).
        if _CHAPTER_NUM_RE.match(title) or _CHAPTER_KEYWORD_RE.match(title):
            # Only assign as chapter if it looks like a top-level entry:
            # either it's at heading level 1, or the number pattern has no dots
            # (e.g. ``3. Linear Models``).
            num_match = _CHAPTER_NUM_RE.match(title)
            if num_match:
                num_str = num_match.group(1)
                # Single integer (no dots) → chapter.
                if "." not in num_str:
                    self._chapter = title
                    self._section = None
                    self._subsection = None
                    return

            if _CHAPTER_KEYWORD_RE.match(title):
                self._chapter = title
                self._section = None
                self._subsection = None
                return

        if _SECTION_KEYWORD_RE.match(title):
            self._section = title
            self._subsection = None


# ── Document-level heading extraction ────────────────────────────────────────

def extract_headings(text: str) -> list[HeadingNode]:
    """Parse all Markdown headings from *text* and return them in order.

    Only lines matching ``^#{1,6}\\s+`` are treated as headings.
    Ambiguous lines (no ``#`` prefix) are **not** force-classified.
    """
    headings: list[HeadingNode] = []
    for line_idx, line in enumerate(text.split("\n")):
        m = _MD_HEADING_RE.match(line.strip())
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append(HeadingNode(level=level, title=title, line_index=line_idx))
    return headings


def split_by_headings(text: str) -> list[tuple[HeadingNode | None, str]]:
    """Split *text* into segments bounded by Markdown headings.

    Returns a list of ``(heading_or_none, segment_text)`` tuples.
    The first segment may have ``heading=None`` if the text begins with
    content before any heading.
    """
    headings = extract_headings(text)
    if not headings:
        return [(None, text)]

    lines = text.split("\n")
    segments: list[tuple[HeadingNode | None, str]] = []

    # Content before the first heading (if any).
    if headings[0].line_index > 0:
        pre_text = "\n".join(lines[: headings[0].line_index]).strip()
        if pre_text:
            segments.append((None, pre_text))

    for i, heading in enumerate(headings):
        start = heading.line_index
        end = headings[i + 1].line_index if i + 1 < len(headings) else len(lines)
        segment_text = "\n".join(lines[start:end]).strip()
        if segment_text:
            segments.append((heading, segment_text))

    return segments
