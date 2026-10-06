import { HttpAgent, randomUUID } from "@ag-ui/client";
import "./styles.css";

type UploadResponse = {
  upload_id: string;
  file_name: string;
  size_bytes: number;
  sha256: string;
};

type WorkflowResult = {
  status: "completed" | "failed";
  message: string;
  output_file?: string;
  download_path?: string;
  task_count: number;
  total_mandays: number;
  warnings: string[];
};

const stepLabels: Record<string, string> = {
  extract_reference_pdf: "Extracting the reference PDF…",
  index_and_retrieve_reference: "Indexing and retrieving reference tasks…",
  reason_over_evidence: "Reasoning over the retrieved evidence…",
  populate_job_card: "Populating the Excel job card…",
};

const root = document.querySelector<HTMLDivElement>("#app");
if (!root) throw new Error("App root not found");

root.innerHTML = `
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">MICROSOFT AGENT FRAMEWORK · FUNCTIONAL WORKFLOW</p>
        <h1>Job Card Builder</h1>
        <p class="subtitle">Upload a manday reference PDF, describe the project, and generate an evidence-linked Excel job card.</p>
      </div>
      <div class="badge"><span></span> AG-UI connected</div>
    </header>

    <section class="panel">
      <form id="job-form">
        <div class="field-grid">
          <label class="field">
            <span>Project name <small>optional</small></span>
            <input id="project-name" maxlength="200" placeholder="e.g., Pump station inspection programme" />
          </label>
          <label class="field file-field">
            <span>Manday reference PDF</span>
            <input id="pdf-file" type="file" accept="application/pdf,.pdf" required />
          </label>
        </div>
        <label class="field">
          <span>Project / job description</span>
          <textarea id="description" minlength="10" maxlength="20000" rows="9" required placeholder="Describe the scope, quantities, locations, deliverables, and any assumptions..."></textarea>
        </label>
        <div class="actions">
          <button id="submit" type="submit">Generate job card</button>
          <p id="status" class="status" aria-live="polite">Ready</p>
        </div>
      </form>
    </section>

    <section id="result" class="panel result hidden" aria-live="polite">
      <div id="result-content"></div>
    </section>

    <section class="steps">
      <article><b>01</b><span>Upload & validate</span></article>
      <article><b>02</b><span>Index in AI Search</span></article>
      <article><b>03</b><span>Reason with evidence</span></article>
      <article><b>04</b><span>Populate Excel</span></article>
      <article><b>05</b><span>Store output</span></article>
    </section>
  </main>
`;

const form = document.querySelector<HTMLFormElement>("#job-form")!;
const submit = document.querySelector<HTMLButtonElement>("#submit")!;
const status = document.querySelector<HTMLParagraphElement>("#status")!;
const result = document.querySelector<HTMLElement>("#result")!;
const resultContent = document.querySelector<HTMLDivElement>("#result-content")!;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  result.classList.add("hidden");
  resultContent.replaceChildren();
  submit.disabled = true;

  try {
    const file = document.querySelector<HTMLInputElement>("#pdf-file")!.files?.[0];
    const description = document.querySelector<HTMLTextAreaElement>("#description")!.value.trim();
    const projectName = document.querySelector<HTMLInputElement>("#project-name")!.value.trim();
    if (!file) throw new Error("Select a PDF file.");
    if (description.length < 10) throw new Error("Enter a more complete project description.");

    setStatus("Uploading and validating PDF…", true);
    const upload = await uploadPdf(file);

    setStatus("Running the deterministic workflow…", true);
    const workflowResult = await runWorkflow(upload, description, projectName);
    renderResult(workflowResult);
    setStatus(workflowResult.status === "completed" ? "Completed" : "Action required", false);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    renderError(message);
    setStatus("Failed", false);
  } finally {
    submit.disabled = false;
  }
});

async function uploadPdf(file: File): Promise<UploadResponse> {
  const data = new FormData();
  data.append("file", file);
  const response = await fetch("/api/uploads", { method: "POST", body: data });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `Upload failed (${response.status}).`);
  }
  return response.json() as Promise<UploadResponse>;
}

async function runWorkflow(
  upload: UploadResponse,
  projectDescription: string,
  projectName: string,
): Promise<WorkflowResult> {
  const agent = new HttpAgent({ url: "/agui" });
  agent.messages.push({
    id: randomUUID(),
    role: "user",
    content: JSON.stringify({
      upload_id: upload.upload_id,
      project_description: projectDescription,
      project_name: projectName || null,
    }),
  });

  let responseText = "";
  let protocolError = "";
  const run = await agent.runAgent(
    {},
    {
      onTextMessageStartEvent() {
        setStatus("Workflow is producing the job card…", true);
      },
      onTextMessageContentEvent({ textMessageBuffer }) {
        // The subscriber provides the complete buffer for the current text
        // message, so assigning it avoids duplicate text after reconnects.
        responseText = textMessageBuffer;
      },
      onStepStartedEvent({ event }) {
        setStatus(stepLabels[event.stepName] ?? `Running ${event.stepName}…`, true);
      },
      onRunErrorEvent({ event }) {
        protocolError = event.message;
      },
    },
  );

  if (protocolError) throw new Error(protocolError);

  // Normal MAF workflow output is streamed as text.  The fallback also
  // supports an AG-UI client/server pair that returns only aggregated
  // messages after the run.
  if (!responseText.trim()) {
    const finalMessage = [...run.newMessages]
      .reverse()
      .find((message) => message.role === "assistant" && typeof message.content === "string");
    responseText = typeof finalMessage?.content === "string" ? finalMessage.content : "";
  }
  if (!responseText.trim()) throw new Error("The AG-UI workflow returned no result.");
  try {
    return parseWorkflowResult(responseText);
  } catch {
    throw new Error(`The workflow returned an unexpected payload: ${responseText.slice(0, 300)}`);
  }
}

function parseWorkflowResult(value: string): WorkflowResult {
  const payload: unknown = JSON.parse(value);
  if (!payload || typeof payload !== "object") throw new Error("Result is not an object.");

  const candidate = payload as Partial<WorkflowResult>;
  if (candidate.status !== "completed" && candidate.status !== "failed") {
    throw new Error("Result has an invalid status.");
  }
  if (typeof candidate.message !== "string") throw new Error("Result has no message.");
  if (typeof candidate.task_count !== "number" || typeof candidate.total_mandays !== "number") {
    throw new Error("Result metrics are invalid.");
  }
  if (
    !Array.isArray(candidate.warnings) ||
    candidate.warnings.some((item) => typeof item !== "string")
  ) {
    throw new Error("Result warnings are invalid.");
  }
  return candidate as WorkflowResult;
}

function renderResult(payload: WorkflowResult): void {
  result.classList.remove("hidden");
  const heading = document.createElement("h2");
  heading.textContent = payload.status === "completed" ? "Job card created" : "Job card not created";
  const message = document.createElement("p");
  message.textContent = payload.message;
  resultContent.append(heading, message);

  if (payload.status === "completed") {
    const metrics = document.createElement("div");
    metrics.className = "metrics";
    metrics.append(metric("Tasks", String(payload.task_count)), metric("Total mandays", payload.total_mandays.toFixed(2)));
    resultContent.append(metrics);
    if (payload.download_path) {
      const link = document.createElement("a");
      link.className = "download";
      link.href = payload.download_path;
      link.textContent = `Download ${payload.output_file ?? "job card"}`;
      resultContent.append(link);
    }
  }

  if (payload.warnings?.length) {
    const warningTitle = document.createElement("h3");
    warningTitle.textContent = "Review notes";
    const list = document.createElement("ul");
    payload.warnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = warning;
      list.append(item);
    });
    resultContent.append(warningTitle, list);
  }
}

function renderError(message: string): void {
  result.classList.remove("hidden");
  const heading = document.createElement("h2");
  heading.textContent = "Unable to create job card";
  const body = document.createElement("p");
  body.textContent = message;
  resultContent.replaceChildren(heading, body);
}

function metric(label: string, value: string): HTMLElement {
  const node = document.createElement("div");
  const number = document.createElement("strong");
  number.textContent = value;
  const caption = document.createElement("span");
  caption.textContent = label;
  node.append(number, caption);
  return node;
}

function setStatus(message: string, active: boolean): void {
  status.textContent = message;
  status.classList.toggle("active", active);
}
