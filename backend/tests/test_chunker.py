from ingestion.chunker import HierarchicalChunker, _infer_artifact_target


def test_chunk_empty_content_returns_nothing():
    chunker = HierarchicalChunker()
    assert chunker.chunk("empty.txt", "") == []
    assert chunker.chunk("whitespace.txt", "   \n\n  ") == []


def test_chunk_small_content_produces_one_parent_and_children():
    # parent_chunk_tokens=10 -> 40 chars, child_chunk_tokens=5 -> 20 chars
    chunker = HierarchicalChunker(child_chunk_tokens=5, parent_chunk_tokens=10)
    content = "word " * 10  # 50 chars, exceeds one child but fits one parent window mostly

    chunks = chunker.chunk("doc.txt", content)

    parents = [c for c in chunks if c.metadata["chunk_type"] == "parent"]
    children = [c for c in chunks if c.metadata["chunk_type"] == "child"]

    assert len(parents) >= 1
    assert len(children) >= 1
    # Every child must reference a parent_id that actually exists among parents
    parent_ids = {p.chunk_id for p in parents}
    for child in children:
        assert child.parent_id in parent_ids
        assert child.metadata["parent_id"] == child.parent_id


def test_chunk_covers_full_content_without_gaps_or_overlap_within_parent():
    chunker = HierarchicalChunker(child_chunk_tokens=5, parent_chunk_tokens=1500)
    content = "alpha beta gamma delta epsilon zeta eta theta iota kappa"

    chunks = chunker.chunk("doc.txt", content)
    parent = next(c for c in chunks if c.metadata["chunk_type"] == "parent")
    children = [c for c in chunks if c.parent_id == parent.chunk_id]

    reconstructed = "".join(
        content[c.metadata["char_start"]:c.metadata["char_end"]].strip() + " "
        for c in sorted(children, key=lambda c: c.metadata["char_start"])
    ).strip()
    # Reconstructed child spans should cover all the distinct words in content
    assert set(reconstructed.split()) == set(content.split())


def test_chunk_metadata_includes_filename_and_doc_type():
    chunker = HierarchicalChunker()
    chunks = chunker.chunk("business_requirements.md", "Some content about scope.")
    assert all(c.metadata["filename"] == "business_requirements.md" for c in chunks)
    assert all(c.metadata["doc_type"] == "md" for c in chunks)


def test_infer_artifact_target_from_filename():
    assert _infer_artifact_target("business_requirements.docx", "") == "BRD"
    assert _infer_artifact_target("functional_spec_fsd.md", "") == "FSD"
    assert _infer_artifact_target("technical_architecture.md", "") == "TSD"


def test_infer_artifact_target_from_content_when_filename_is_generic():
    brd_text = "This covers business objectives and stakeholder needs. " * 3
    assert _infer_artifact_target("doc1.txt", brd_text) == "BRD"

    tsd_text = "The api exposes a schema and database endpoint for clients. " * 3
    assert _infer_artifact_target("doc2.txt", tsd_text) == "TSD"


def test_infer_artifact_target_defaults_to_all_when_no_signal():
    assert _infer_artifact_target("misc.txt", "Just some unrelated prose.") == "ALL"
