import { ArrowLeftRight, Play, Square } from "lucide-react";
import { post, type AppState } from "../api";

export default function Controls({ state }: { state: AppState }) {
  const running = state.monitoring !== "idle";
  const { settings, metrics } = state;

  return (
    <section className="flex flex-wrap items-end gap-x-4 gap-y-2 rounded-lg border border-line bg-surface px-3 py-2.5">
      <button
        onClick={() => post(running ? "/api/monitoring/stop" : "/api/monitoring/start")}
        className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 font-medium text-white ${
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
          disabled={state.models.length === 0}
          onChange={(e) => post("/api/model/select", { name: e.target.value })}
        >
          {state.models.length === 0 && <option value="">Geen vision-model</option>}
          {state.models.map((model) => (
            <option key={model.name} value={model.name}>
              {model.name}
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

      <button
        onClick={() => post("/api/cameras/swap")}
        className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-muted hover:text-ink"
      >
        <ArrowLeftRight size={14} /> Wissel camera's
      </button>

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
