from core.config import get_settings
from graph.nodes import advance_section, route_after_advance, route_after_evaluation
from graph.state import SectionDraft, SectionPlan

settings = get_settings()


def _toc():
    return [
        SectionPlan(section_id="1", title="Intro", description="", target_artifact_filter="ALL"),
        SectionPlan(section_id="2", title="Body", description="", target_artifact_filter="ALL"),
    ]


def _state(draft: SectionDraft, idx: int = 0):
    return {
        "toc": _toc(),
        "current_section_idx": idx,
        "sections": [draft],
    }


def test_route_after_evaluation_redrafts_when_failed_and_retries_remain():
    draft = SectionDraft(section_id="1", title="Intro", passed_critic=False, retry_count=0)
    assert route_after_evaluation(_state(draft)) == "draft_section"


def test_route_after_evaluation_advances_when_passed():
    draft = SectionDraft(section_id="1", title="Intro", passed_critic=True, retry_count=1)
    assert route_after_evaluation(_state(draft)) == "advance_section"


def test_route_after_evaluation_advances_when_max_retries_hit_even_if_failed():
    draft = SectionDraft(
        section_id="1", title="Intro",
        passed_critic=False,
        retry_count=settings.max_retries_per_section,
    )
    assert route_after_evaluation(_state(draft)) == "advance_section"


def test_advance_section_moves_pointer_and_emits_event():
    state = {
        "toc": _toc(),
        "current_section_idx": 0,
        "events": [],
    }
    result = advance_section(state)
    assert result["current_section_idx"] == 1
    assert "status" not in result
    assert any("section 2" in e for e in result["events"])


def test_advance_section_triggers_compiling_status_on_last_section():
    state = {
        "toc": _toc(),
        "current_section_idx": 1,
        "events": [],
    }
    result = advance_section(state)
    assert result["current_section_idx"] == 2
    assert result["status"] == "compiling"


def test_route_after_advance_continues_to_retrieve_context_when_sections_remain():
    state = {"toc": _toc(), "current_section_idx": 1}
    assert route_after_advance(state) == "retrieve_context"


def test_route_after_advance_compiles_when_all_sections_done():
    state = {"toc": _toc(), "current_section_idx": 2}
    assert route_after_advance(state) == "compile_document"
