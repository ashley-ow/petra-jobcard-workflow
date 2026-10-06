# Architecture and deterministic controls

## Runtime flow

```text
Browser (AG-UI HttpAgent)
  ├─ POST /api/uploads (multipart PDF)
  └─ POST /agui (AG-UI RunAgentInput; user message is WorkflowRequest JSON)
        ↓
Microsoft Agent Framework Functional Workflow (`@workflow`)
  1. Resolve and validate uploaded PDF
  2. Extract page text and deterministic overlapping chunks
  3. Create/check Azure AI Search index and upsert chunks
  4. Retrieve document-scoped evidence with Azure AI Search
  5. Run a structured-output reasoning agent
  6. Validate exact quotes/pages and calculate totals in Python Decimal
  7. Copy and populate the named-range Excel template
  8. Store output under data/output and return JSON through AG-UI
```

## Determinism boundary

The graph/order, schemas, evidence checks, formulas, file naming rules, and calculations are deterministic. The Azure OpenAI reasoning step is constrained by temperature 0, a fixed seed, a fixed prompt, strict Pydantic structured output, document-scoped retrieval, exact-quote checks, and code-side totals. Model inference itself is not guaranteed to be bit-for-bit identical by the service. If regulatory repeatability is required, persist the model deployment/version, prompt, retrieved chunks, and validated structured plan for replay.

## PDF and search design

The sample extracts text client-side with `pypdf` and uploads chunks directly with the Azure AI Search data-plane SDK. This avoids indexer/skillset dependencies and works with the Serverless Developer preview as well as dedicated services. Image-only PDFs are rejected with an actionable OCR message.

The index is shared, while every chunk is filtered by the PDF SHA-256 `document_id`. This prevents evidence from one uploaded PDF being used for another job card.

## Excel template contract

The workbook must contain one-cell workbook-level named ranges:

| Name | Meaning |
|---|---|
| `ProjectName` | Output project title |
| `ProjectDescription` | Original UI text |
| `GeneratedAt` | UTC timestamp |
| `SourcePdf` | Uploaded source filename |
| `ReviewNotes` | Assumptions and warnings |
| `JobTableStart` | First cell of a 10-column task area |
| `TotalMandays` | Summary total formula cell |

Starting at `JobTableStart`, columns are: item, job task, matched reference task, quantity, unit, mandays/unit, total mandays, reference page, evidence/rationale, and review status. The template must have `TEMPLATE_TASK_CAPACITY` preformatted rows.

## Production extensions

- Put uploads and outputs in Blob Storage and the registry in a durable database.
- Add Entra ID authentication and per-user authorization to upload/output endpoints.
- Add malware scanning, content-type inspection, retention, audit records, and Key Vault.
- Add Azure Document Intelligence OCR for scans and complex tables.
- Add OpenTelemetry and a queue for long-running documents.
- Replace local workbook writes with a locked/idempotent output store when scaling horizontally.
