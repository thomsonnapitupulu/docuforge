import pytest

from api.job_store import JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(str(tmp_path / "jobs.db"))


def test_create_and_get(store):
    store.create("job-1", "BRD")
    job = store.get("job-1")
    assert job["job_id"] == "job-1"
    assert job["status"] == "running"
    assert job["artifact_type"] == "BRD"
    assert job["sections_complete"] == 0
    assert job["total_sections"] == 0
    assert job["events"] == []
    assert job["final_document"] is None
    assert job["error"] is None


def test_get_missing_job_returns_none(store):
    assert store.get("does-not-exist") is None


def test_update_persists_fields_including_events_list(store):
    store.create("job-2", "FSD")
    store.update(
        "job-2",
        status="done",
        total_sections=3,
        sections_complete=3,
        events=["a", "b"],
        final_document="# Doc",
    )
    job = store.get("job-2")
    assert job["status"] == "done"
    assert job["total_sections"] == 3
    assert job["events"] == ["a", "b"]
    assert job["final_document"] == "# Doc"


def test_update_rejects_unknown_field(store):
    store.create("job-3", "TSD")
    with pytest.raises(ValueError, match="Unknown job field"):
        store.update("job-3", not_a_real_column="x")


def test_update_with_no_fields_is_a_no_op(store):
    store.create("job-4", "BRD")
    store.update("job-4")  # should not raise
    assert store.get("job-4")["status"] == "running"


def test_survives_reopening_the_same_db_file(tmp_path):
    """The whole point of this store: state must survive a process restart."""
    db_path = str(tmp_path / "jobs.db")
    JobStore(db_path).create("job-5", "BRD")

    reopened = JobStore(db_path)
    job = reopened.get("job-5")
    assert job is not None
    assert job["artifact_type"] == "BRD"
