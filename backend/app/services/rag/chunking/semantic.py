"""
semantic.py
===========
Boundary-aware semantic splitting and lightweight type tagging.

Responsibilities:
- Split section text along natural semantic boundaries (heading →
  paragraph → sentence) rather than arbitrary N-character windows.
- Protect atomic content: formulas, tables, and code blocks are never
  split mid-unit.
- Keep related content together: definition + explanation, formula +
  context, example + explanation, wherever they fit within the target size.
- Assign a ``SemanticType`` tag as metadata-only (never affects
  boundaries, sizing, retrieval, or content).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.rag.chunking.models import (
    ChunkingConfig,
    HierarchyContext,
    SemanticType,
    count_tokens,
)


# ── Compiled patterns for semantic type classification ───────────────────────

_FORMULA_INDICATORS = re.compile(
    r"(\$\$|\\\[|\\begin\{equation\}|\\begin\{align\})",
)
_STANDALONE_EQUATION_RE = re.compile(
    r"^[A-Za-z\s]*[=<>≤≥±∓∞∑∏∫√]+",
    re.MULTILINE,
)

_DEFINITION_RE = re.compile(
    r"\b(is defined as|refers to|(?:can be )?defined as|Definition\s*:)\b",
    re.IGNORECASE,
)
_BOLD_DEF_RE = re.compile(r"\*\*[^*]+\*\*\s*[:–—-]")

_EXAMPLE_RE = re.compile(
    r"\b(for example|for instance|example\s*\d*\s*[:.\-]|consider the following)\b",
    re.IGNORECASE,
)

_NUMERICAL_RE = re.compile(
    r"\b(calculate|find the value|determine|solve for|compute|evaluate)\b",
    re.IGNORECASE,
)

_APPLICATION_RE = re.compile(
    r"\b(applications?\s+of|applied\s+in|real[- ]world|industrial\s+use)\b",
    re.IGNORECASE,
)

_EXPLANATION_RE = re.compile(
    r"\b(because|therefore|as a result|thus|hence|the mechanism behind|"
    r"this is due to|the reason is|consequently)\b",
    re.IGNORECASE,
)

# ── Atomic block detection ───────────────────────────────────────────────────

_TABLE_LINE_RE = re.compile(r"^\s*\|.+\|")
_FENCED_CODE_RE = re.compile(r"^```")
_LATEX_BLOCK_START = re.compile(r"^\$\$")
_LATEX_BLOCK_END = re.compile(r"\$\$\s*$")

# Sentence boundary: period/question/exclamation followed by whitespace and
# an uppercase letter (avoids splitting abbreviations like "Dr." or "U.S.").
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SemanticChunk:
    """A boundary-aware text segment with metadata annotations."""

    text: str
    hierarchy: HierarchyContext
    semantic_type: SemanticType = SemanticType.GENERAL
    page_numbers: list[int] = field(default_factory=list)


# ── Semantic type classifier ─────────────────────────────────────────────────

def classify_semantic_type(text: str) -> SemanticType:
    """Return a best-effort ``SemanticType`` for *text*.

    This is purely a metadata annotation — it never alters the text or
    influences chunk boundaries.
    """
    # Check formula indicators first (they tend to be short and specific).
    if _FORMULA_INDICATORS.search(text):
        return SemanticType.FORMULA
    if _STANDALONE_EQUATION_RE.search(text) and len(text.strip().splitlines()) <= 3:
        return SemanticType.FORMULA

    if _DEFINITION_RE.search(text) or _BOLD_DEF_RE.search(text):
        return SemanticType.DEFINITION

    if _NUMERICAL_RE.search(text):
        return SemanticType.NUMERICAL

    if _EXAMPLE_RE.search(text):
        return SemanticType.EXAMPLE

    if _APPLICATION_RE.search(text):
        return SemanticType.APPLICATION

    if _EXPLANATION_RE.search(text):
        return SemanticType.EXPLANATION

    # ``concept`` is reserved for headings that introduce fundamental terms.
    # Without deeper analysis we fall back to ``general``.
    return SemanticType.GENERAL


# ── Atomic block grouping ────────────────────────────────────────────────────

def _group_atomic_blocks(paragraphs: list[str]) -> list[str]:
    """Merge paragraphs that form atomic units (tables, fenced code, LaTeX blocks).

    Adjacent table rows, fenced code blocks, and ``$$…$$`` blocks are
    merged into single strings so they are never split mid-unit.
    """
    merged: list[str] = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        lines = para.split("\n")

        # Fenced code block spanning multiple paragraphs.
        if _FENCED_CODE_RE.match(lines[0].strip()):
            block_lines = list(lines)
            # If the closing fence is not in the same paragraph, gather more.
            if not any(_FENCED_CODE_RE.match(ln.strip()) for ln in lines[1:]):
                i += 1
                while i < len(paragraphs):
                    block_lines.append("")
                    block_lines.extend(paragraphs[i].split("\n"))
                    if any(
                        _FENCED_CODE_RE.match(ln.strip())
                        for ln in paragraphs[i].split("\n")
                    ):
                        break
                    i += 1
            merged.append("\n".join(block_lines))
            i += 1
            continue

        # LaTeX display block ``$$…$$`` spanning multiple paragraphs.
        if _LATEX_BLOCK_START.match(lines[0].strip()):
            block_lines = list(lines)
            if not _LATEX_BLOCK_END.search(lines[-1].strip()) or len(lines) == 1:
                # check if it's a single-line $$ ... $$ block
                first_stripped = lines[0].strip()
                if not (first_stripped.startswith("$$") and first_stripped.endswith("$$") and len(first_stripped) > 4):
                    i += 1
                    while i < len(paragraphs):
                        block_lines.append("")
                        block_lines.extend(paragraphs[i].split("\n"))
                        if _LATEX_BLOCK_END.search(paragraphs[i].strip()):
                            break
                        i += 1
            merged.append("\n".join(block_lines))
            i += 1
            continue

        # Table rows — merge consecutive table paragraphs.
        if _TABLE_LINE_RE.match(lines[0]):
            table_lines = list(lines)
            i += 1
            while i < len(paragraphs):
                next_lines = paragraphs[i].split("\n")
                if _TABLE_LINE_RE.match(next_lines[0]):
                    table_lines.append("")
                    table_lines.extend(next_lines)
                    i += 1
                else:
                    break
            merged.append("\n".join(table_lines))
            continue

        merged.append(para)
        i += 1

    return merged


# ── Core splitting logic ─────────────────────────────────────────────────────

class SemanticSplitter:
    """Splits section text into semantic chunks of approximately
    ``config.target_chunk_size`` tokens.

    Boundaries are chosen in preference order: paragraph (``\\n\\n``),
    then sentence (``[.!?]\\s+[A-Z]``).  Atomic blocks (tables, formulas,
    code) are kept intact even if they exceed the target size.
    """

    def __init__(self, config: ChunkingConfig) -> None:
        self.config = config

    def split_section(
        self,
        text: str,
        hierarchy: HierarchyContext,
        page_numbers: list[int] | None = None,
    ) -> list[SemanticChunk]:
        """Split *text* into semantic chunks under the target token size.

        Parameters
        ----------
        text : str
            Section text (may contain multiple paragraphs, tables, etc.).
        hierarchy : HierarchyContext
            Active hierarchy context for this section.
        page_numbers : list[int] | None
            Page numbers associated with this section.

        Returns
        -------
        list[SemanticChunk]
        """
        if not text or not text.strip():
            return []

        pages = page_numbers or []
        target = self.config.target_chunk_size
        overlap = self.config.chunk_overlap

        # 1. Split into paragraphs on double-newline boundaries.
        raw_paragraphs = re.split(r"\n{2,}", text)
        raw_paragraphs = [p for p in raw_paragraphs if p.strip()]

        if not raw_paragraphs:
            return []

        # 2. Group atomic blocks (tables, code, LaTeX) so they stay intact.
        paragraphs = _group_atomic_blocks(raw_paragraphs)

        # 3. Accumulate paragraphs into chunks up to target size.
        chunks: list[SemanticChunk] = []
        current_parts: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = count_tokens(para, self.config)

            # If this single paragraph exceeds target, flush current
            # accumulator, then handle the oversized paragraph.
            if para_tokens > target:
                # Flush what we have so far.
                if current_parts:
                    chunks.append(self._make_chunk(
                        "\n\n".join(current_parts), hierarchy, pages,
                    ))
                    current_parts.clear()
                    current_tokens = 0

                # Split oversized paragraph at sentence boundaries.
                sub_chunks = self._split_oversized(para, target, overlap)
                for sc in sub_chunks:
                    chunks.append(self._make_chunk(sc, hierarchy, pages))
                continue

            # Would adding this paragraph exceed the target?
            # Account for the double-newline join.
            join_cost = count_tokens("\n\n", self.config) if current_parts else 0
            if current_tokens + join_cost + para_tokens > target and current_parts:
                # Flush accumulator.
                chunks.append(self._make_chunk(
                    "\n\n".join(current_parts), hierarchy, pages,
                ))
                # Keep overlap: carry the last paragraph forward if it fits.
                if overlap > 0 and current_parts:
                    last = current_parts[-1]
                    last_tokens = count_tokens(last, self.config)
                    if last_tokens <= overlap:
                        current_parts = [last]
                        current_tokens = last_tokens
                    else:
                        current_parts = []
                        current_tokens = 0
                else:
                    current_parts = []
                    current_tokens = 0

            current_parts.append(para)
            current_tokens += (join_cost + para_tokens)

        # Flush remaining content.
        if current_parts:
            chunks.append(self._make_chunk(
                "\n\n".join(current_parts), hierarchy, pages,
            ))

        return chunks

    # ── Private helpers ──────────────────────────────────────────────────────

    def _make_chunk(
        self,
        text: str,
        hierarchy: HierarchyContext,
        page_numbers: list[int],
    ) -> SemanticChunk:
        return SemanticChunk(
            text=text.strip(),
            hierarchy=hierarchy,
            semantic_type=classify_semantic_type(text),
            page_numbers=list(page_numbers),
        )

    def _split_oversized(
        self,
        text: str,
        target: int,
        overlap: int,
    ) -> list[str]:
        """Split an oversized paragraph at sentence boundaries with overlap."""
        sentences = _SENTENCE_BOUNDARY_RE.split(text)
        if len(sentences) <= 1:
            # Cannot split further — return as-is (atomic).
            return [text]

        result: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for sent in sentences:
            sent_tokens = count_tokens(sent, self.config)
            join_cost = 1 if current_parts else 0  # space between sentences

            if current_tokens + join_cost + sent_tokens > target and current_parts:
                result.append(" ".join(current_parts))

                # Overlap: carry trailing sentences forward.
                overlap_parts: list[str] = []
                overlap_tokens = 0
                for s in reversed(current_parts):
                    s_tok = count_tokens(s, self.config)
                    if overlap_tokens + s_tok <= overlap:
                        overlap_parts.insert(0, s)
                        overlap_tokens += s_tok
                    else:
                        break

                current_parts = overlap_parts
                current_tokens = overlap_tokens

            current_parts.append(sent)
            current_tokens += join_cost + sent_tokens

        if current_parts:
            result.append(" ".join(current_parts))

        return result
