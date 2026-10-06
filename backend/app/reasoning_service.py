from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .config import Settings, reveal
from .models import CalculatedTask, ReasoningPlan, SearchEvidence, ValidatedJobPlan, WorkflowRequest

_SYSTEM_INSTRUCTIONS = """You are a job-planning analyst. Convert a project description into job-card rows by matching work to the supplied PDF excerpts.

Rules:
1. Use only reference tasks and manday values present in the supplied excerpts.
2. source_quote must be an exact, short quotation from the cited excerpt and must include the manday value.
3. source_page must match the excerpt page. Never invent a page, task, or manday value.
4. If no reliable reference exists, set matched_reference_task and source_quote and source_page to null, unit_mandays to 0, confidence below 0.5, and review_required to true.
5. Decompose the project into discrete, non-overlapping rows. Quantity is the number of units; unit_mandays is mandays per unit.
6. Do not calculate totals. The workflow calculates totals deterministically.
7. Return only the configured structured output.
"""


class ReasoningService:
    def __init__(self, settings: Settings) -> None:
        # Imported lazily so pure validation tests do not need Azure/MAF clients.
        # The Azure OpenAI integration lives in agent-framework-openai.  It is
        # not exposed from the old ``agent_framework.azure`` namespace.
        from agent_framework import Agent
        from agent_framework.openai import OpenAIChatCompletionClient
        from azure.identity import DefaultAzureCredential

        client_kwargs: dict[str, Any] = {
            "azure_endpoint": "https://aaf-common-dev-001.openai.azure.com", #settings.azure_openai_endpoint,
            # For Azure OpenAI, MAF's ``model`` is the deployment name.
            "model": "gpt-5.4-mini", #settings.azure_openai_deployment,
            "api_version": "2025-04-01-preview", #settings.azure_openai_api_version,
        }
        if settings.azure_openai_api_key is not None:
            client_kwargs["api_key"] = reveal(settings.azure_openai_api_key)
        else:
            client_kwargs["credential"] = DefaultAzureCredential()

        client = OpenAIChatCompletionClient(**client_kwargs)
        self.agent = Agent(
            client=client,
            name="job-card-reasoner",
            instructions=_SYSTEM_INSTRUCTIONS,
        )
        # Model request options belong on Agent.run(), not Agent().  Keeping
        # them here makes every reasoning call use the same typed output and
        # deterministic sampling settings.
        self.run_options: dict[str, Any] = {
            "response_format": ReasoningPlan,
            "temperature": 0,
            "seed": settings.reasoning_seed,
        }
        self.strict_citations = settings.strict_citations
        
        self.max_context_chars = settings.max_reasoning_context_chars

    async def reason(
        self,
        request: WorkflowRequest,
        evidence: list[SearchEvidence],
    ) -> ValidatedJobPlan:
        prompt = self._build_prompt(request, evidence)
        response = await self.agent.run(prompt, options=self.run_options)
        value = response.value
        if isinstance(value, ReasoningPlan):
            plan = value
        elif isinstance(value, Mapping):
            plan = ReasoningPlan.model_validate(value)
        else:
            text = response.text
            if not text:
                raise ValueError("The reasoning agent returned no structured output.")
            plan = ReasoningPlan.model_validate_json(text)
        #return validate_and_calculate(plan, evidence, self.strict_citations)
        return validate_and_calculate(plan, evidence, False)

    def _build_prompt(self, request: WorkflowRequest, evidence: list[SearchEvidence]) -> str:
        excerpts: list[str] = []
        used = 0
        for item in evidence:
            block = (
                f"\n--- EXCERPT page={item.page_number} chunk={item.chunk_number} "
                f"score={item.score or 0:.4f} ---\n{item.content}\n"
            )
            if used + len(block) > self.max_context_chars:
                break
            excerpts.append(block)
            used += len(block)
        if not excerpts:
            raise ValueError("No reference excerpts fit in the reasoning context window.")

        return (
            f"PROJECT NAME: {request.project_name or 'Derive a concise title'}\n"
            f"PROJECT/JOB DESCRIPTION:\n{request.project_description}\n\n"
            "REFERENCE EXCERPTS FROM THE UPLOADED PDF:\n"
            + "".join(excerpts)
        )


def validate_and_calculate(
    plan: ReasoningPlan,
    evidence: list[SearchEvidence],
    strict_citations: bool,
) -> ValidatedJobPlan:
    page_text: dict[int, str] = {}
    for item in evidence:
        page_text[item.page_number] = page_text.get(item.page_number, "") + "\n" + item.content

    warnings = list(plan.warnings)
    calculated_tasks: list[CalculatedTask] = []
    for index, task in enumerate(plan.tasks, start=1):
        task_warnings: list[str] = []
        if task.source_page is None or task.source_quote is None:
            if task.unit_mandays != 0:
                task_warnings.append("uncited task has a non-zero manday value")
        else:
            normalized_quote = normalize_for_match(task.source_quote)
            normalized_page = normalize_for_match(page_text.get(task.source_page, ""))
            if not normalized_quote or normalized_quote not in normalized_page:
                task_warnings.append(
                    f"source quote was not found verbatim in retrieved page {task.source_page}"
                )
            if not number_appears_in_text(task.unit_mandays, task.source_quote):
                task_warnings.append("source quote does not contain the unit manday value")

        if task_warnings and strict_citations:
            details = ", ".join(task_warnings)
            #raise ValueError(f"Warning:Evidence validation failed for task {index}: {details}")
            print(f"Warning:Evidence validation failed for task {index}: {details}")        
        if task_warnings:
            warnings.extend(f"Task {index}: {warning}." for warning in task_warnings)
            task = task.model_copy(update={"review_required": True})

        total = (Decimal(str(task.quantity)) * Decimal(str(task.unit_mandays))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        calculated_tasks.append(
            CalculatedTask(**task.model_dump(), calculated_total_mandays=float(total))
        )

    total_mandays = sum(Decimal(str(task.calculated_total_mandays)) for task in calculated_tasks)
    total_mandays = total_mandays.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ValidatedJobPlan(
        project_title=plan.project_title,
        project_summary=plan.project_summary,
        tasks=calculated_tasks,
        assumptions=plan.assumptions,
        warnings=deduplicate(warnings),
        total_mandays=float(total_mandays),
    )


def normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def number_appears_in_text(value: float, text: str) -> bool:
    expected = Decimal(str(value)).normalize()
    for token in re.findall(r"(?<![A-Za-z0-9])\d+(?:,\d{3})*(?:\.\d+)?", text):
        try:
            if Decimal(token.replace(",", "")).normalize() == expected:
                return True
        except ArithmeticError:
            continue
    return False


def deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item.strip()))
