"""
Test isolation: point Chroma at a throwaway directory and provide a dummy
Anthropic key so importing graph.nodes (which builds these clients at module
import time) never touches real data or credentials during test collection.
Must run before any project module is imported.
"""

import os
import tempfile

os.environ["CHROMA_PERSIST_DIR"] = tempfile.mkdtemp(prefix="docuforge_test_chroma_")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
