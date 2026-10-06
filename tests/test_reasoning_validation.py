from backend.app.models import ReasonedTask, ReasoningPlan, SearchEvidence
from backend.app.reasoning_service import validate_and_calculate


def test_validate_and_calculate_uses_decimal_rounding() -> None:
    evidence = [
        SearchEvidence(
            chunk_id="doc-p00001-c0001",
            document_id="doc",
            source_file="reference.pdf",
            page_number=1,
            chunk_number=1,
            content="Valve inspection | 1.25 mandays per valve",
            score=1.0,
        )
    ]
    plan = ReasoningPlan(
        project_title="Valve programme",
        project_summary="Inspect valves",
        tasks=[
            ReasonedTask(
                job_task="Inspect valves",
                matched_reference_task="Valve inspection",
                rationale="Direct match",
                quantity=3,
                unit="valves",
                unit_mandays=1.25,
                source_page=1,
                source_quote="Valve inspection | 1.25 mandays per valve",
                confidence=0.98,
                review_required=False,
            )
        ],
        assumptions=[],
        warnings=[],
    )
    result = validate_and_calculate(plan, evidence, strict_citations=True)
    assert result.tasks[0].calculated_total_mandays == 3.75
    assert result.total_mandays == 3.75
