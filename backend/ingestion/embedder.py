"""
Embedder & Vector Store Manager.

Uses ChromaDB with two collections:
- "child_chunks"  → embedded, used for semantic similarity search
- "parent_chunks" → stored by ID, retrieved after child match (not embedded)

Retrieval strategy (Parent-Child RAG):
1. Semantic search on child_chunks to find relevant child IDs.
2. Look up their parent_id, fetch full parent content for LLM context.
"""

import time

import chromadb
from chromadb.config import Settings as ChromaSettings
from utils.logger import get_logger

from ingestion.chunker import Chunk
from core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


class VectorStoreManager:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        # Child chunks: semantically indexed
        self.child_col = self.client.get_or_create_collection(
            name="child_chunks",
            metadata={"hnsw:space": "cosine"}
        )
        # Parent chunks: stored as documents, retrieved by ID
        self.parent_col = self.client.get_or_create_collection(
            name="parent_chunks",
            metadata={"hnsw:space": "cosine"}
        )

    def warm_up(self) -> None:
        """
        Forces Chroma's default embedding function to initialize now instead
        of on the first real request. It downloads an ONNX model
        (~/.cache/chroma/onnx_models — a user-level cache, independent of
        CHROMA_PERSIST_DIR) on first use: near-instant once cached, but
        60-90+ seconds on a genuinely fresh environment (a clean container
        with no pre-warmed cache), which would otherwise make a real user's
        first request look like a hang. Call once at process startup.
        """
        start = time.monotonic()
        self.child_col.query(query_texts=["warm up embedding model"], n_results=1)
        logger.info("vector_store_warmed_up", seconds=round(time.monotonic() - start, 2))

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        """Store both parent and child chunks into their respective collections."""
        parent_chunks = [c for c in chunks if c.metadata["chunk_type"] == "parent"]
        child_chunks  = [c for c in chunks if c.metadata["chunk_type"] == "child"]

        if parent_chunks:
            self.parent_col.upsert(
                ids=[c.chunk_id for c in parent_chunks],
                documents=[c.content for c in parent_chunks],
                metadatas=[c.metadata for c in parent_chunks],
            )
            logger.info("upserted_parents", count=len(parent_chunks))

        if child_chunks:
            self.child_col.upsert(
                ids=[c.chunk_id for c in child_chunks],
                documents=[c.content for c in child_chunks],
                metadatas=[c.metadata for c in child_chunks],
            )
            logger.info("upserted_children", count=len(child_chunks))

    def retrieve_context(
        self,
        query: str,
        artifact_type: str,
        top_k: int = None
    ) -> str:
        """
        Hybrid retrieval:
        1. Search child_chunks with optional artifact_type filter.
        2. Gather unique parent_ids from results.
        3. Fetch full parent content → assemble into context string.
        """
        top_k = top_k or settings.retrieval_top_k

        # Build metadata filter
        where = {}
        if artifact_type and artifact_type != "ALL":
            where = {
                "$or": [
                    {"target_artifact": {"$eq": artifact_type}},
                    {"target_artifact": {"$eq": "ALL"}}
                ]
            }

        results = self.child_col.query(
            query_texts=[query],
            n_results=top_k,
            where=where if where else None,
            include=["documents", "metadatas", "distances"]
        )

        if not results["ids"][0]:
            logger.warning("no_results_found", query=query[:80], artifact=artifact_type)
            return ""

        # Collect unique parent IDs
        parent_ids = list({
            meta["parent_id"]
            for meta in results["metadatas"][0]
            if meta.get("parent_id")
        })

        if not parent_ids:
            # Fall back to child content directly
            return "\n\n---\n\n".join(results["documents"][0])

        # Retrieve full parent chunks
        parent_results = self.parent_col.get(
            ids=parent_ids,
            include=["documents", "metadatas"]
        )

        context_blocks = []
        for doc, meta in zip(parent_results["documents"], parent_results["metadatas"]):
            context_blocks.append(
                f"[Source: {meta['filename']}]\n{doc}"
            )

        logger.info(
            "context_retrieved",
            query=query[:80],
            child_hits=len(results["ids"][0]),
            parent_chunks=len(context_blocks)
        )

        return "\n\n---\n\n".join(context_blocks)

    def get_reference_sample(self, max_chars: int = 6000) -> str:
        """Return a sample of stored documents for the planning prompt."""
        results = self.parent_col.get(limit=10, include=["documents", "metadatas"])
        blocks = []
        total = 0
        for doc, meta in zip(results["documents"], results["metadatas"]):
            snippet = doc[:600]
            block = f"[{meta['filename']}]\n{snippet}"
            blocks.append(block)
            total += len(block)
            if total >= max_chars:
                break
        return "\n\n---\n\n".join(blocks)

    def collection_stats(self) -> dict:
        return {
            "child_chunks": self.child_col.count(),
            "parent_chunks": self.parent_col.count(),
        }

    def clear_all(self) -> None:
        """Wipe all stored chunks (use with caution)."""
        self.client.delete_collection("child_chunks")
        self.client.delete_collection("parent_chunks")
        self.child_col = self.client.get_or_create_collection("child_chunks")
        self.parent_col = self.client.get_or_create_collection("parent_chunks")
        logger.warning("vector_store_cleared")
