from fastapi.testclient import TestClient

from api import main as main_module

client = TestClient(main_module.app)


def test_cancel_returns_404_for_unknown_job():
    resp = client.post("/jobs/does-not-exist/cancel")
    assert resp.status_code == 404


def test_cancel_returns_400_when_job_is_not_running():
    main_module.job_store.create("job-done", "BRD")
    main_module.job_store.update("job-done", status="done")

    resp = client.post("/jobs/job-done/cancel")
    assert resp.status_code == 400
    assert "not running" in resp.json()["detail"]


def test_cancel_marks_a_running_job_as_cancelling():
    main_module.job_store.create("job-running", "BRD")

    resp = client.post("/jobs/job-running/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelling"
    assert main_module.job_store.get("job-running")["status"] == "cancelling"


def test_run_graph_with_cancellation_stops_at_next_node_boundary(monkeypatch):
    """The core cooperative-cancellation loop: once a job is marked
    'cancelling' (as the /cancel endpoint does), the graph stream must stop
    consuming further steps and return a 'cancelled' final state."""

    def fake_stream(initial_state, stream_mode="values", config=None):
        yield {"step": 1}
        yield {"step": 2}
        yield {"step": 3}  # must never be reached

    monkeypatch.setattr(main_module, "generation_graph", type(
        "FakeGraph", (), {"stream": staticmethod(fake_stream)}
    ))

    job_id = "job-cancel-unit"
    main_module.job_store.create(job_id, "BRD")

    call_count = {"n": 0}
    real_get = main_module.job_store.get

    def get_that_cancels_on_second_check(jid):
        call_count["n"] += 1
        if call_count["n"] >= 2:  # cancel takes effect on the check after step 2
            main_module.job_store.update(jid, status="cancelling")
        return real_get(jid)

    monkeypatch.setattr(main_module.job_store, "get", get_that_cancels_on_second_check)

    result = main_module._run_graph_with_cancellation(job_id, {"step": 0})

    assert result["status"] == "cancelled"
    assert result["step"] == 2  # stopped there — step 3 was never consumed
    assert call_count["n"] == 2  # confirms the loop didn't even reach step 3's check


def test_run_graph_with_cancellation_runs_to_completion_when_never_cancelled(monkeypatch):
    def fake_stream(initial_state, stream_mode="values", config=None):
        yield {"step": 1}
        yield {"step": 2, "status": "done"}

    monkeypatch.setattr(main_module, "generation_graph", type(
        "FakeGraph", (), {"stream": staticmethod(fake_stream)}
    ))

    job_id = "job-no-cancel"
    main_module.job_store.create(job_id, "BRD")

    result = main_module._run_graph_with_cancellation(job_id, {"step": 0})
    assert result == {"step": 2, "status": "done"}
