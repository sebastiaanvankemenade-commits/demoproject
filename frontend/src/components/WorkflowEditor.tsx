import { ArrowDown, ArrowUp, Copy, Download, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { post, request, type AppState, type WorkflowDefinition, type WorkflowStepDefinition } from "../api";

const uniqueId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1296).toString(36)}`;

function blankStep(): WorkflowStepDefinition {
  return {
    id: uniqueId("stap"),
    title: "",
    instruction: "",
    completion_criterion: "",
    expected_objects: [],
    deviation_conditions: [],
    required_confirmations: null,
    requires_transition: false,
    expected_turns: null,
  };
}

function blankWorkflow(): WorkflowDefinition {
  return { schema_version: 1, id: uniqueId("wf"), name: "", required_confirmations: 3, steps: [blankStep()] };
}

export default function WorkflowEditor({ state, openId }: { state: AppState; openId?: string | null }) {
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [draft, setDraft] = useState<WorkflowDefinition | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const importInput = useRef<HTMLInputElement>(null);

  async function reload() {
    const { data } = await request<WorkflowDefinition[]>("/api/workflows", "GET");
    if (data) setWorkflows(data);
    return data;
  }

  useEffect(() => {
    reload().then((data) => {
      const wanted = data?.find((workflow) => workflow.id === openId);
      if (wanted) {
        edit(wanted);
        setAdvanced(true);
      }
    });
  }, [openId]);

  function edit(workflow: WorkflowDefinition) {
    setDraft(structuredClone(workflow));
    setNotice(null);
  }

  async function persist(workflow: WorkflowDefinition, success: string) {
    const { error } = await request("/api/workflows", "POST", workflow);
    setNotice(error ? { text: error, error: true } : { text: success, error: false });
    await reload();
    return !error;
  }

  async function duplicate(workflow: WorkflowDefinition) {
    const copy = { ...structuredClone(workflow), id: uniqueId("wf"), name: `${workflow.name} (kopie)` };
    if (await persist(copy, "Kopie gemaakt.")) setDraft(copy);
  }

  async function remove(workflow: WorkflowDefinition) {
    if (!window.confirm(`"${workflow.name}" verwijderen?`)) return;
    const { error } = await request(`/api/workflows/${workflow.id}`, "DELETE");
    setNotice(error ? { text: error, error: true } : { text: "Verwijderd.", error: false });
    if (!error && draft?.id === workflow.id) setDraft(null);
    await reload();
  }

  function exportFile(workflow: WorkflowDefinition) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(workflow, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${workflow.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function importFile(file: File) {
    try {
      await persist(JSON.parse(await file.text()), "Werkinstructie geïmporteerd.");
    } catch {
      setNotice({ text: "Dit bestand is geen geldige werkinstructie.", error: true });
    }
  }

  return (
    <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-auto p-3 lg:grid-cols-[320px_minmax(0,1fr)] lg:overflow-hidden">
      <aside className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-3 py-2">
          <h1 className="font-medium">Werkinstructies</h1>
          <div className="flex gap-1">
            <IconButton label="Importeren" onClick={() => importInput.current?.click()}>
              <Upload size={14} />
            </IconButton>
            <IconButton label="Nieuwe werkinstructie" onClick={() => edit(blankWorkflow())}>
              <Plus size={14} />
            </IconButton>
          </div>
          <input
            ref={importInput}
            type="file"
            accept="application/json"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) importFile(file);
              event.target.value = "";
            }}
          />
        </div>
        <ul className="min-h-0 flex-1 overflow-auto p-2">
          {workflows.map((workflow) => (
            <li key={workflow.id} className={`rounded-md p-2 ${draft?.id === workflow.id ? "bg-raised" : ""}`}>
              <button onClick={() => edit(workflow)} className="w-full text-left">
                <span className="block font-medium">{workflow.name}</span>
                <span className="text-[12px] text-muted">
                  {workflow.steps.length} {workflow.steps.length === 1 ? "stap" : "stappen"}
                  {workflow.id === state.workflow.id && " · actief"}
                </span>
              </button>
              <div className="mt-1 flex gap-1">
                {workflow.id !== state.workflow.id && (
                  <button
                    onClick={() => post("/api/workflow/select", { name: workflow.id })}
                    className="text-[12px] text-live hover:underline"
                  >
                    Activeren
                  </button>
                )}
                <span className="flex-1" />
                <IconButton label="Dupliceren" onClick={() => duplicate(workflow)}>
                  <Copy size={13} />
                </IconButton>
                <IconButton label="Exporteren" onClick={() => exportFile(workflow)}>
                  <Download size={13} />
                </IconButton>
                <IconButton label="Verwijderen" onClick={() => remove(workflow)}>
                  <Trash2 size={13} />
                </IconButton>
              </div>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
        {!draft ? (
          <p className="p-4 text-muted">Kies een werkinstructie of maak een nieuwe.</p>
        ) : (
          <Form
            draft={draft}
            advanced={advanced}
            notice={notice}
            active={draft.id === state.workflow.id}
            onAdvanced={setAdvanced}
            onChange={setDraft}
            onSave={() => persist(draft, "Opgeslagen.")}
          />
        )}
      </section>
    </main>
  );
}

interface FormProps {
  draft: WorkflowDefinition;
  advanced: boolean;
  active: boolean;
  notice: { text: string; error: boolean } | null;
  onAdvanced: (value: boolean) => void;
  onChange: (workflow: WorkflowDefinition) => void;
  onSave: () => void;
}

function Form({ draft, advanced, active, notice, onAdvanced, onChange, onSave }: FormProps) {
  function setStep(index: number, changes: Partial<WorkflowStepDefinition>) {
    onChange({ ...draft, steps: draft.steps.map((step, i) => (i === index ? { ...step, ...changes } : step)) });
  }

  function move(index: number, offset: number) {
    const steps = [...draft.steps];
    const [step] = steps.splice(index, 1);
    steps.splice(index + offset, 0, step);
    onChange({ ...draft, steps });
  }

  return (
    <>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {draft.id.startsWith("voorgedaan-") && (
          <p className="mb-3 rounded-md border border-doubt/40 px-3 py-2 text-[13px] text-doubt">
            Gemaakt uit een voorbeeld. Controleer elke stap, vooral wat er zichtbaar moet zijn, voordat je hem activeert.
          </p>
        )}
        <div className="flex flex-wrap items-end gap-4">
          <Text label="Naam werkinstructie" value={draft.name} onChange={(name) => onChange({ ...draft, name })} wide />
          <label className="flex items-center gap-1.5 pb-1.5 text-[13px] text-muted">
            <input type="checkbox" checked={advanced} onChange={(event) => onAdvanced(event.target.checked)} />
            Geavanceerd
          </label>
        </div>
        {advanced && (
          <label className="mt-3 flex w-52 flex-col gap-1 text-[12px] text-muted">
            Bevestigingen per stap
            <input
              type="number"
              min={1}
              max={10}
              value={draft.required_confirmations}
              onChange={(event) => onChange({ ...draft, required_confirmations: Number(event.target.value) })}
              className="rounded-md border border-line bg-raised px-2 py-1 text-[14px] text-ink"
            />
          </label>
        )}

        <ol className="mt-4 flex flex-col gap-3">
          {draft.steps.map((step, index) => (
            <li key={step.id} className="rounded-md border border-line p-3">
              <div className="mb-2 flex items-center gap-1">
                <span className="mr-auto text-[13px] text-muted">Stap {index + 1}</span>
                <IconButton label="Omhoog" disabled={index === 0} onClick={() => move(index, -1)}>
                  <ArrowUp size={13} />
                </IconButton>
                <IconButton label="Omlaag" disabled={index === draft.steps.length - 1} onClick={() => move(index, 1)}>
                  <ArrowDown size={13} />
                </IconButton>
                <IconButton
                  label="Stap verwijderen"
                  disabled={draft.steps.length === 1}
                  onClick={() => onChange({ ...draft, steps: draft.steps.filter((_, i) => i !== index) })}
                >
                  <Trash2 size={13} />
                </IconButton>
              </div>
              <div className="flex flex-col gap-2">
                <Text label="Titel" value={step.title} onChange={(title) => setStep(index, { title })} />
                <Text
                  label="Instructie voor de operator"
                  value={step.instruction}
                  onChange={(instruction) => setStep(index, { instruction })}
                />
                <Text
                  label="Wat moet zichtbaar zijn als de stap klaar is?"
                  value={step.completion_criterion}
                  onChange={(completion_criterion) => setStep(index, { completion_criterion })}
                />
                {advanced && (
                  <>
                    <Text
                      label="Verwachte objecten (komma's)"
                      value={step.expected_objects.join(", ")}
                      onChange={(text) =>
                        setStep(index, {
                          expected_objects: text.split(",").map((item) => item.trimStart()).filter(Boolean),
                        })
                      }
                    />
                    <Text
                      label="Mogelijke afwijkingen (komma's). Niet: een onderdeel dat nog niet geplaatst is."
                      value={step.deviation_conditions.join(", ")}
                      onChange={(text) =>
                        setStep(index, {
                          deviation_conditions: text.split(",").map((item) => item.trimStart()).filter(Boolean),
                        })
                      }
                    />
                    <label className="flex items-center gap-1.5 text-[13px] text-muted">
                      <input
                        type="checkbox"
                        checked={step.requires_transition}
                        onChange={(event) => setStep(index, { requires_transition: event.target.checked })}
                      />
                      Stap moet eerst onafgerond gezien zijn
                    </label>
                    <label className="flex w-72 flex-col gap-1 text-[12px] text-muted">
                      Draaibewegingen tellen (leeg = niet tellen)
                      <input
                        type="number"
                        min={1}
                        max={100}
                        value={step.expected_turns ?? ""}
                        onChange={(event) =>
                          setStep(index, { expected_turns: event.target.value ? Number(event.target.value) : null })
                        }
                        className="rounded-md border border-line bg-raised px-2 py-1 text-[14px] text-ink"
                      />
                    </label>
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>

        <button
          onClick={() => onChange({ ...draft, steps: [...draft.steps, blankStep()] })}
          className="mt-3 flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[13px] text-muted hover:text-ink"
        >
          <Plus size={13} /> Stap toevoegen
        </button>
      </div>

      <footer className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-2.5">
        <button onClick={onSave} className="rounded-md bg-live/85 px-3 py-1.5 font-medium text-white hover:bg-live">
          Opslaan
        </button>
        {active && <span className="text-[13px] text-doubt">Opslaan herstart deze actieve werkinstructie.</span>}
        {notice && <span className={`text-[13px] ${notice.error ? "text-fault" : "text-done"}`}>{notice.text}</span>}
      </footer>
    </>
  );
}

function Text({
  label,
  value,
  onChange,
  wide,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  wide?: boolean;
}) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 text-[12px] text-muted ${wide ? "flex-1" : ""}`}>
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-line bg-raised px-2.5 py-1.5 text-[14px] text-ink"
      />
    </label>
  );
}

function IconButton({ label, children, ...props }: { label: string } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className="rounded p-1 text-muted hover:bg-raised hover:text-ink disabled:opacity-30"
    >
      {children}
    </button>
  );
}
