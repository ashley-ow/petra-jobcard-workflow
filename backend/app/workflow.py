from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from agent_framework import step, workflow
from pydantic import ValidationError

from .config import Settings
from .excel_service import ExcelJobCardWriter
from .models import (
    ReferenceChunk,
    SearchEvidence,
    UploadedFileRecord,
    ValidatedJobPlan,
    WorkflowRequest,
    WorkflowResult,
)
from .pdf_service import extract_pdf_chunks
from .reasoning_service import ReasoningService
from .search_service import AzureSearchReferenceStore
from .storage import FileRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkflowRuntime:
    settings: Settings
    registry: FileRegistry
    search: AzureSearchReferenceStore
    reasoner: ReasoningService
    excel: ExcelJobCardWriter


_runtime: WorkflowRuntime | None = None


def configure_runtime(runtime: WorkflowRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> WorkflowRuntime:
    """Return the configured dependencies used by the functional workflow steps."""

    if _runtime is None:
        raise RuntimeError("Workflow runtime has not been configured.")
    return _runtime


#def parse_workflow_request(message: str) -> WorkflowRequest:
#    try:
#        payload = json.loads(message)
#    except json.JSONDecodeError as exc:
#        raise ValueError("The AG-UI message must contain a JSON workflow request.") from exc
#    return WorkflowRequest.model_validate(payload)
def parse_workflow_request(message):
    #
    # AG-UI passes conversation history
    #
    if isinstance(message, list):
        if not message:
            raise ValueError("AG-UI message list is empty.")
        msg = message[-1]

        #
        # agent_framework._types.Message
        #
        if hasattr(msg, "contents"):
            if not msg.contents:
                raise ValueError(
                    "Message contains no content."
                )
            content = msg.contents[0]

            #
            # Extract the payload from whatever
            # field the installed SDK uses.
            #
            payload_text = None
            for field_name in [
                "text",
                "value",
                "data",
                "content"
            ]:
                if hasattr(content, field_name):

                    value = getattr(
                        content,
                        field_name
                    )

                    if value:
                        payload_text = value
                        break
            #
            # Last resort
            #
            if payload_text is None:
                attrs = vars(content)
                for value in attrs.values():
                    if isinstance(value, str):
                        payload_text = value
                        break

            if payload_text is None:
                raise ValueError(
                    f"Unable to locate payload in "
                    f"content object: {vars(content)}"
                )

            payload = json.loads(payload_text)
        else:
            raise ValueError(
                f"Unsupported message object: "
                f"{type(msg)}"
            )
    elif isinstance(message, str):
        payload = json.loads(message)
    elif isinstance(message, dict):
        payload = message
    else:
        raise ValueError(
            f"Unsupported message type: "
            f"{type(message)}"
        )

    return WorkflowRequest.model_validate(
        payload
    )

@dataclass(slots=True)
class ExtractedReference:
    request: WorkflowRequest
    upload: UploadedFileRecord
    chunks: list[ReferenceChunk]


@dataclass(slots=True)
class RetrievedReference:
    request: WorkflowRequest
    upload: UploadedFileRecord
    evidence: list[SearchEvidence]


@dataclass(slots=True)
class ReasonedJobCard:
    request: WorkflowRequest
    upload: UploadedFileRecord
    plan: ValidatedJobPlan


@step
async def extract_reference_pdf(request: WorkflowRequest) -> ExtractedReference:
    """Resolve the upload and extract page-aware text chunks from the PDF."""

    runtime = get_runtime()
    upload = runtime.registry.get(request.upload_id)
    chunks = await asyncio.to_thread(
        extract_pdf_chunks,
        Path(upload.stored_path),
        upload.sha256,
        upload.original_name,
        runtime.settings.pdf_chunk_chars,
        runtime.settings.pdf_chunk_overlap,
    )
    return ExtractedReference(request=request, upload=upload, chunks=chunks)


@step
async def index_and_retrieve_reference(extracted: ExtractedReference) -> RetrievedReference:
    """Index the document and retrieve excerpts relevant to the job description."""

    runtime = get_runtime()
    await asyncio.to_thread(runtime.search.ensure_index)
    await asyncio.to_thread(runtime.search.index_chunks, extracted.chunks)
    evidence = await asyncio.to_thread(
        runtime.search.search,
        extracted.request.project_description,
        extracted.upload.sha256,
        runtime.settings.search_top_k,
    )
    return RetrievedReference(
        request=extracted.request,
        upload=extracted.upload,
        evidence=evidence,
    )


@step
async def reason_over_evidence(retrieved: RetrievedReference) -> ReasonedJobCard:
    """Run the Microsoft Agent Framework reasoning agent and validate its evidence."""

    plan = await get_runtime().reasoner.reason(retrieved.request, retrieved.evidence)
    return ReasonedJobCard(request=retrieved.request, upload=retrieved.upload, plan=plan)


@step
async def populate_job_card(reasoned: ReasonedJobCard) -> WorkflowResult:
    """Populate the Excel template and return the downloadable workflow result."""

    output = await asyncio.to_thread(
        get_runtime().excel.write,
        reasoned.plan,
        reasoned.request.project_description,
        reasoned.upload,
    )
    return WorkflowResult(
        status="completed",
        message="Job card created successfully.",
        output_file=output.name,
        download_path=f"/api/outputs/{quote(output.name)}",
        task_count=len(reasoned.plan.tasks),
        total_mandays=reasoned.plan.total_mandays,
        warnings=reasoned.plan.warnings,
    )


@workflow
async def job_card_workflow(message: str) -> str:
    """Run the observable job-card pipeline and return one AG-UI text payload."""

    try:
        #for troubleshooting
        print("MESSAGE TYPE:", type(message))

        if isinstance(message, list):
            print("LIST LENGTH:", len(message))

            if len(message) > 0:
                print("FIRST ITEM TYPE:", type(message[0]))
                print("FIRST ITEM:", message[0])

        print("RAW MESSAGE:", message)

        request = parse_workflow_request(message)
        extracted = await extract_reference_pdf(request)
        retrieved = await index_and_retrieve_reference(extracted)
        reasoned = await reason_over_evidence(retrieved)
        result = await populate_job_card(reasoned)
    except (ValueError, KeyError, FileNotFoundError, ValidationError) as exc:
        logger.warning("Workflow rejected input: %s", exc)
        result = WorkflowResult(status="failed", message=str(exc))
    except Exception as exc:  # noqa: BLE001 - boundary returns a safe failure to AG-UI
        logger.exception("Workflow failed")
        result = WorkflowResult(
            status="failed",
            message="Workflow execution failed. Review the backend log for the underlying error.",
        )
    return result.model_dump_json()
