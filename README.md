# Microsoft Agent Framework Job Card Sample

A complete local sample for a deterministic **Microsoft Agent Framework Functional Workflow** exposed through **AG-UI**. It accepts a manday-reference PDF and a project/job description, indexes the PDF in Azure AI Search, reasons over retrieved evidence, populates an Excel job card, and stores the result locally.

## What is included

- Python 3.11 FastAPI backend
- Microsoft Agent Framework `@workflow` Functional API with observable `@step` stages
- Microsoft Agent Framework structured-output Azure OpenAI agent
- Microsoft Agent Framework AG-UI FastAPI endpoint
- TypeScript AG-UI `HttpAgent` browser client
- Azure AI Search direct ingestion, compatible with Serverless Developer preview and Dedicated tiers
- Named-range-driven Excel template and sample workbook
- Strict evidence/page/quote validation and Python-side manday calculations
- Unit tests and VS Code launch/tasks

## Prerequisites

1. Python 3.11 or newer.
2. Node.js 20 or newer and npm.
3. An Azure AI Search service. The Serverless Developer tier is currently a preview with regional/feature/SLA constraints; a dedicated service also works.
4. An Azure OpenAI resource and a chat deployment that supports structured output.
5. Either resource API keys, or Azure CLI authentication (`az login`) plus suitable data-plane roles.

Official references:

- Functional Workflow API: https://learn.microsoft.com/agent-framework/concepts/workflows/functional
- AG-UI integration: https://learn.microsoft.com/agent-framework/integrations/by-component/ui/ag-ui/
- AG-UI workflow hosting: https://learn.microsoft.com/agent-framework/integrations/by-component/ui/ag-ui/workflows
- Azure AI Search pricing models: https://learn.microsoft.com/azure/search/search-sku-tier
- Azure AI Search Python SDK: https://learn.microsoft.com/python/api/overview/azure/search-documents-readme

## Setup in VS Code

From the project root:

```powershell
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
```

On macOS/Linux, activate with `source .venv/bin/activate` and copy with `cp .env.example .env`.

Edit `.env`:

```dotenv
AZURE_SEARCH_ENDPOINT=https://gptkb-q6f7jlnpp6tnk.search.windows.net
AZURE_SEARCH_INDEX_NAME=job-card-reference
AZURE_SEARCH_API_KEY=YOUR-KEY

AZURE_OPENAI_ENDPOINT=https://YOUR-AOAI-RESOURCE.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=YOUR-CHAT-DEPLOYMENT
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_API_KEY=YOUR-KEY
```

To use Entra ID instead, leave both key variables blank, run `az login`, and grant the identity permissions for search index/data operations and Azure OpenAI inference.

Install and run the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Run the backend in a second terminal from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.server:app --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:5173. The Vite dev server proxies `/api` and `/agui` to the Python backend.

### VS Code shortcuts

- Run/debug **Backend: FastAPI + MAF workflow** from `.vscode/launch.json`.
- Run task **Frontend: AG-UI dev server**.
- Run task **Tests**.

## Workflow implementation

`backend/app/workflow.py` contains the functional workflow:

```python
@workflow
async def job_card_workflow(message: str) -> str:
    request = parse_workflow_request(message)
    extracted = await extract_reference_pdf(request)
    retrieved = await index_and_retrieve_reference(extracted)
    reasoned = await reason_over_evidence(retrieved)
    result = await populate_job_card(reasoned)
    return result.model_dump_json()
```

Each stage is decorated with `@step`, so the framework emits workflow step events that the
browser displays as live progress. The built workflow is wrapped with
`AgentFrameworkWorkflow` and registered at `/agui` using
`add_agent_framework_fastapi_endpoint`.

The UI first uploads the PDF through `/api/uploads`, then sends this JSON as the AG-UI user message:

```json
{
  "upload_id": "returned-by-upload-endpoint",
  "project_description": "Inspect 12 valves and produce reports...",
  "project_name": "Valve inspection programme"
}
```

## Using your own Excel template

The included `templates/job_card_template.xlsx` is ready to use. To substitute your template:

1. Preserve or create these workbook-level named ranges: `ProjectName`, `ProjectDescription`, `GeneratedAt`, `SourcePdf`, `ReviewNotes`, `JobTableStart`, and `TotalMandays`.
2. At `JobTableStart`, provide 10 columns in this order: item, task, matched reference task, quantity, unit, mandays/unit, total mandays, reference page, evidence/rationale, status.
3. Preformat at least `TEMPLATE_TASK_CAPACITY` rows (default 40), or lower that setting.
4. Set `TEMPLATE_PATH` in `.env`.

See `ARCHITECTURE.md` for the exact contract. The script `scripts/create_sample_template.py` regenerates the sample template.

## Tests

```powershell
pytest
ruff check backend tests
```

The unit tests do not call Azure. A live end-to-end test requires your configured Azure resources and a real reference PDF.

## Important behavior and limitations

- Workflow orchestration and calculations are deterministic; model inference is constrained but not mathematically guaranteed to be bit-for-bit repeatable.
- The sample uses lexical Azure AI Search retrieval to avoid a second embedding deployment. Add vector fields/embeddings if your reference terminology needs semantic matching.
- `pypdf` handles text PDFs. Image-only/scanned PDFs require OCR; Azure Document Intelligence is the recommended production extension.
- Azure AI Search Serverless Developer is a preview and is not recommended for production workloads without validating preview constraints.
- Local `data/` storage is suitable for development, not multi-instance production deployment.
- Generated rows marked `REVIEW` and all warnings should be confirmed by a responsible human before commercial or operational use.
