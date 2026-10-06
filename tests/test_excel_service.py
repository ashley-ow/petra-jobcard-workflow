from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

from backend.app.excel_service import ExcelJobCardWriter
from backend.app.models import CalculatedTask, UploadedFileRecord, ValidatedJobPlan


def test_populates_template(tmp_path: Path) -> None:
    template = Path("templates/job_card_template.xlsx")
    writer = ExcelJobCardWriter(template, tmp_path, task_capacity=40)
    plan = ValidatedJobPlan(
        project_title="Valve programme",
        project_summary="Inspect three valves",
        tasks=[
            CalculatedTask(
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
                calculated_total_mandays=3.75,
            )
        ],
        assumptions=[],
        warnings=[],
        total_mandays=3.75,
    )
    source = UploadedFileRecord(
        upload_id="12345678",
        original_name="reference.pdf",
        stored_path="/tmp/reference.pdf",
        sha256="a" * 64,
        size_bytes=100,
        uploaded_at=datetime.now(timezone.utc),
    )
    output = writer.write(plan, "Inspect three valves", source)
    workbook = load_workbook(output, data_only=False)
    sheet = workbook["Job Card"]
    assert sheet["B4"].value == "Valve programme"
    assert sheet["B12"].value == "Inspect valves"
    assert sheet["G12"].value == "=ROUND(D12*F12,2)"
    assert sheet["H5"].value == "=SUM('Job Card'!G12:G51)"
