"""
Hierarchical Parent-Child Chunker.

Strategy:
- Parent chunks (~1500 tokens): full context windows for LLM generation.
- Child chunks (~250 tokens): precise units for semantic vector search.
- Each child stores a reference to its parent ID so we can retrieve full context.

Metadata schema per chunk:
{
    "chunk_id": str,
    "parent_id": str | None,
    "chunk_type": "parent" | "child",
    "filename": str,
    "doc_type": str,             # inferred from filename/content
    "target_artifact": str,      # "BRD" | "FSD" | "TSD" | "ALL"
    "char_start": int,
    "char_end": int
}
"""

import re
import uuid
from dataclasses import dataclass
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)

# Rough token-to-char ratio (1 token ≈ 4 chars in English)
CHARS_PER_TOKEN = 4


@dataclass
class Chunk:
    chunk_id: str
    content: str
    metadata: dict
    parent_id: Optional[str] = None


def _infer_artifact_target(filename: str, content: str) -> str:
    """
    Heuristic: guess which artifact type this doc primarily feeds.
    Checks filename keywords, then content keywords.
    """
    name = filename.lower()
    text = content[:2000].lower()

    if any(k in name for k in ["business", "brd", "requirements", "scope", "stakeholder"]):
        return "BRD"
    if any(k in name for k in ["functional", "fsd", "feature", "user_story", "usecase"]):
        return "FSD"
    if any(k in name for k in ["technical", "tsd", "architecture", "api", "schema", "infra", "db"]):
        return "TSD"

    # Content-level fallback
    brd_signals = text.count("business") + text.count("stakeholder") + text.count("objective")
    fsd_signals = text.count("feature") + text.count("user story") + text.count("acceptance")
    tsd_signals = text.count("api") + text.count("schema") + text.count("endpoint") + text.count("database")

    scores = {"BRD": brd_signals, "FSD": fsd_signals, "TSD": tsd_signals}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "ALL"


def _split_into_sentences(text: str) -> list[str]:
    """Naive sentence splitter — splits on .\n or double newlines."""
    # Split on paragraph boundaries first
    paragraphs = re.split(r"\n{2,}", text)
    sentences = []
    for para in paragraphs:
        # Further split long paragraphs on sentence endings
        parts = re.split(r"(?<=[.!?])\s+", para.strip())
        sentences.extend([p for p in parts if p.strip()])
    return sentences


class HierarchicalChunker:
    """
    Produces parent + child chunk pairs from a RawDocument.
    """

    def __init__(
        self,
        child_chunk_tokens: int = 250,
        parent_chunk_tokens: int = 1500,
    ):
        self.child_size = child_chunk_tokens * CHARS_PER_TOKEN
        self.parent_size = parent_chunk_tokens * CHARS_PER_TOKEN

    def chunk(self, filename: str, content: str) -> list[Chunk]:
        if not content.strip():
            logger.warning("empty_document", filename=filename)
            return []

        target_artifact = _infer_artifact_target(filename, content)
        doc_type = filename.rsplit(".", 1)[-1].lower()

        logger.info(
            "chunking_document",
            filename=filename,
            content_length=len(content),
            inferred_target=target_artifact
        )

        chunks: list[Chunk] = []
        pos = 0

        while pos < len(content):
            # ── Parent chunk ──────────────────────────────────────────────
            parent_end = min(pos + self.parent_size, len(content))
            # Snap to a word boundary
            if parent_end < len(content):
                snap = content.rfind(" ", pos, parent_end)
                if snap > pos:
                    parent_end = snap

            parent_text = content[pos:parent_end].strip()
            if not parent_text:
                pos = parent_end
                continue

            parent_id = str(uuid.uuid4())
            parent_chunk = Chunk(
                chunk_id=parent_id,
                content=parent_text,
                parent_id=None,
                metadata={
                    "chunk_id": parent_id,
                    "parent_id": "",
                    "chunk_type": "parent",
                    "filename": filename,
                    "doc_type": doc_type,
                    "target_artifact": target_artifact,
                    "char_start": pos,
                    "char_end": parent_end,
                }
            )
            chunks.append(parent_chunk)

            # ── Child chunks (within parent window) ───────────────────────
            child_pos = pos
            while child_pos < parent_end:
                child_end = min(child_pos + self.child_size, parent_end)
                if child_end < parent_end:
                    snap = content.rfind(" ", child_pos, child_end)
                    if snap > child_pos:
                        child_end = snap

                child_text = content[child_pos:child_end].strip()
                if child_text:
                    child_id = str(uuid.uuid4())
                    child_chunk = Chunk(
                        chunk_id=child_id,
                        content=child_text,
                        parent_id=parent_id,
                        metadata={
                            "chunk_id": child_id,
                            "parent_id": parent_id,
                            "chunk_type": "child",
                            "filename": filename,
                            "doc_type": doc_type,
                            "target_artifact": target_artifact,
                            "char_start": child_pos,
                            "char_end": child_end,
                        }
                    )
                    chunks.append(child_chunk)

                child_pos = child_end

            pos = parent_end

        logger.info(
            "chunking_complete",
            filename=filename,
            total_chunks=len(chunks),
            parent_count=sum(1 for c in chunks if c.metadata["chunk_type"] == "parent"),
            child_count=sum(1 for c in chunks if c.metadata["chunk_type"] == "child"),
        )

        return chunks
