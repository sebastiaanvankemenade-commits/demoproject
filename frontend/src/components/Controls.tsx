import { ArrowLeftRight, Camera, FlaskConical, ListPlus, Play, Square } from "lucide-react";
import { post, request, type AppState } from "../api";

async function startDemo() {
  const name = window.prompt("Naam van de nieuwe werkinstructie");
  if (!name?.trim()) return;
  const parts = window.prompt("Hoe heten de onderdelen? Met komma's, bijvoorbeeld: barrel, shaft, flight. Mag leeg.") ?? "";
  const { error } = await request("/api/demo/start", "POST", { name, parts: parts.split(",") });
  if (error) window.alert(error);
}

async function saveSnapshot() {
  const name = window.prompt("Naam voor deze testopname, bijvoorbeeld stap1-goed");
  if (!name) return;
  const { error } = await request("/api/snapshots", "POST", { name });
  if (error) window.alert(error);
}

export default function Controls({ state }: { state: AppState }) {
  const running = state.monitoring !== "idle";
  const { settings, metrics } = state;

  return (
    <section className="flex flex-wrap items-end gap-x-4 gap-y-2 rounded-lg border border-line bg-surface px-3 py-2.5">
      <button
        disabled={state.simulated || state.switching_model || !!state.demo}
        onClick={() => post(running ? "/api/monitoring/stop" : "/api/monitoring/start")}
        className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium text-white disabled:opacity-40 ${
          running ? "bg-fault/85 hover:bg-fault" : "bg-live/85 hover:bg-live"
        }`}
      >
        {running ? <Square size={14} /> : <Play size={14} />}
        {running ? "Stop monitoring" : "Start monitoring"}
      </button>

      <Field label="Werkinstructie">
        <select value={state.workflow.id} onChange={(e) => post("/api/workflow/select", { name: e.target.value })}>
          {state.workflows.map((workflow) => (
            <option key={workflow.id} value={workflow.id}>
              {workflow.name}
            </option>
          ))}
        </select>
      </Field>

      <Field label="AI-model">
        <select
          value={settings.model ?? ""}
          disabled={state.models.length === 0 || state.switching_model}
          onChange={(e) => post("/api/model/select", { name: e.target.value })}
        >
          {state.models.length === 0 && <option value="">Geen vision-model</option>}
          {state.models.map((model) => (
            <option key={model.name} value={model.name} disabled={!model.fits}>
              {model.name}
              {!model.fits && " (te groot)"}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Analyse met">
        <select value={settings.camera_mode} onChange={(e) => post("/api/settings", { camera_mode: e.target.value })}>
          <option value="both">Beide camera's</option>
          <option value="1">Alleen bovenaanzicht</option>
          <option value="2">Alleen zijaanzicht</option>
        </select>
      </Field>

      <Field label="Minimale interval">
        <select value={settings.interval_s} onChange={(e) => post("/api/settings", { interval_s: Number(e.target.value) })}>
          {[1, 2, 3, 5, 10].map((seconds) => (
            <option key={seconds} value={seconds}>
              {seconds} s
            </option>
          ))}
        </select>
      </Field>

      <label
        className="flex items-center gap-1.5 pb-1.5 text-[13px] text-muted"
        title="Het model tekent vakken om wat het ziet. Dit kost per analyse een extra modelaanvraag."
      >
        <input
          type="checkbox"
          checked={settings.show_boxes}
          onChange={(e) => post("/api/settings", { show_boxes: e.target.checked })}
        />
        Vakken tonen
      </label>

      {state.test_source && (
        <Field label="Testscène">
          <select
            value={state.test_source.scene ?? ""}
            onChange={(e) => post("/api/test-source/scene", { name: e.target.value })}
          >
            {state.test_source.scenes.map((scene) => (
              <option key={scene} value={scene}>
                {scene}
              </option>
            ))}
          </select>
        </Field>
      )}

      <Secondary onClick={() => post("/api/cameras/swap")}>
        <ArrowLeftRight size={14} /> Wissel camera's
      </Secondary>
      <Secondary onClick={startDemo} disabled={!!state.demo || state.simulated} title="Doe de stappen voor; de app maakt er een werkinstructie van">
        <ListPlus size={14} /> Voordoen
      </Secondary>
      <Secondary onClick={saveSnapshot}>
        <Camera size={14} /> Testopname
      </Secondary>
      <Secondary onClick={() => post("/api/simulation", { enabled: !state.simulated })}>
        <FlaskConical size={14} /> {state.simulated ? "Simulatie uit" : "Simulatie"}
      </Secondary>

      <dl className="ml-auto flex gap-4 text-[13px] tabular-nums">
        <Metric label="Laatste analyse" value={seconds(metrics.last_s)} />
        <Metric label="Gemiddeld" value={seconds(metrics.average_s)} />
        <Metric label="Werkelijke interval" value={seconds(metrics.actual_interval_s)} />
        <Metric label="Ongeldig" value={String(metrics.invalid)} />
      </dl>
    </section>
  );
}

const seconds = (value: number | null) => (value === null ? "—" : `${value.toFixed(1)} s`);

function Secondary({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-muted hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[12px] text-muted">
      {label}
      {children}
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}
