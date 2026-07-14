"""
Test isolation: point Chroma and the job store at throwaway locations and
provide a dummy Anthropic key so importing graph.nodes / api.main (which
build these clients/stores at module import time) never touches real data
or credentials during test collection. Must run before any project module
is imported.
"""

import os
import tempfile

os.environ["CHROMA_PERSIST_DIR"] = tempfile.mkdtemp(prefix="docuforge_test_chroma_")
os.environ["JOB_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="docuforge_test_jobs_"), "jobs.db"
)
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
