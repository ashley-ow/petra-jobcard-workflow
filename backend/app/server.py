from __future__ import annotations

import hashlib
from pathlib import Path

from agent_framework.ag_ui import AgentFrameworkWorkflow, add_agent_framework_fastapi_endpoint
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .excel_service import ExcelJobCardWriter
from .reasoning_service import ReasoningService
from .search_service import AzureSearchReferenceStore
from .storage import FileRegistry, safe_filename
from .workflow import WorkflowRuntime, configure_runtime, job_card_workflow

settings = Settings()
settings.ensure_directories()
registry = FileRegistry(settings.upload_dir, settings.registry_path)

runtime = WorkflowRuntime(
    settings=settings,
    registry=registry,
    search=AzureSearchReferenceStore(settings),
    reasoner=ReasoningService(settings),
    excel=ExcelJobCardWriter(
        settings.template_path,
        settings.output_dir,
        settings.template_task_capacity,
    ),
)
configure_runtime(runtime)
workflow_instance = job_card_workflow.build()
agui_workflow = AgentFrameworkWorkflow(
    workflow=workflow_instance,
    name="job-card-workflow",
    description="Create an evidence-linked Excel job card from a reference PDF.",
)

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Register the Microsoft Agent Framework workflow as an AG-UI server.  The
# explicit adapter makes it clear that the endpoint is hosting a workflow
# (and therefore emits workflow step events), not a single chat agent.
add_agent_framework_fastapi_endpoint(app, agui_workflow, "/agui")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "workflow": "microsoft-agent-framework-functional-api",
        "ui_protocol": "AG-UI",
    }


@app.post("/api/uploads")
async def upload_pdf(file: UploadFile = File(...)) -> dict:
    original_name = safe_filename(file.filename or "reference.pdf", fallback="reference.pdf")
    if Path(original_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted.")
    content = await file.read(settings.max_pdf_bytes + 1)
    if len(content) > settings.max_pdf_bytes:
        raise HTTPException(status_code=413, detail="PDF exceeds the configured size limit.")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF header.")
    digest = hashlib.sha256(content).hexdigest()
    record = registry.register(original_name, content, digest)
    return {
        "upload_id": record.upload_id,
        "file_name": record.original_name,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
    }


@app.get("/api/outputs/{file_name}")
def download_output(file_name: str) -> FileResponse:
    safe_name = safe_filename(file_name)
    output = settings.output_dir / safe_name
    try:
        resolved = output.resolve(strict=True)
        output_root = settings.output_dir.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Output file not found.") from exc
    if output_root not in resolved.parents or resolved.suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="Invalid output path.")
    return FileResponse(
        resolved,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=resolved.name,
    )


if settings.frontend_dist.exists():
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "message": (
                    "Backend is running. Start the Vite frontend on port 5173 "
                    "or build frontend/dist."
                ),
                "agui_endpoint": "/agui",
            }
        )
