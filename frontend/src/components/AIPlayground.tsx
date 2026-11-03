import { Loader2, Send } from "lucide-react";
import { useState } from "react";
import { request, type AppState, type PlaygroundResult, type PlaygroundRun } from "../api";

const EXAMPLES = [
  "Welke onderdelen liggen op tafel?",
  "Is de bout verwijderd uit de montageplaat?",
  "Waar bevindt de sluitring zich ten opzichte van de bout?",
  "Is de vleugelmoer zichtbaar gemonteerd?",
];

export default function AIPlayground({ state }: { state: AppState }) {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const [first, setFirst] = useState(state.settings.model ?? "");
  const [second, setSecond] = useState("");
  const [cameraMode, setCameraMode] = useState("both");
  const [structured, setStructured] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<PlaygroundRun | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    const models = [first, second].filter(Boolean);
    const result = await request<PlaygroundRun>("/api/playground", "POST", {
      models,
      question,
      camera_mode: cameraMode,
      structured,
    });
    if (result.data) setRun(result.data);
    setError(result.error ?? null);
    setBusy(false);
  }

  return (
    <main className="min-h-0 flex-1 overflow-auto p-3">
      <div className="mx-auto flex max-w-5xl flex-col gap-3">
        <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4">
          <div>
            <h1 className="text-base font-medium">AI Playground</h1>
            <p className="text-[13px] text-muted">
              Test een model op de huidige beelden. Dit heeft geen invloed op de actieve werkinstructie.
            </p>
          </div>
          <label className="flex flex-col gap-1 text-[12px] text-muted">
            Vraag
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={2}
              className="rounded-md border border-line bg-raised px-2.5 py-2 text-[14px] text-ink"
            />
          </label>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                onClick={() => setQuestion(example)}
                className="rounded-full border border-line px-2.5 py-0.5 text-[12px] text-muted hover:text-ink"
              >
                {example}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <Field label="Model A">
              <ModelSelect state={state} value={first} onChange={setFirst} />
            </Field>
            <Field label="Model B (vergelijken)">
              <ModelSelect state={state} value={second} onChange={setSecond} optional />
            </Field>
            <Field label="Beeld">
              <select value={cameraMode} onChange={(event) => setCameraMode(event.target.value)}>
                <option value="both">Beide camera's</option>
                <option value="1">Bovenaanzicht</option>
                <option value="2">Zijaanzicht</option>
              </select>
            </Field>
            <label className="flex items-center gap-1.5 pb-1.5 text-[13px] text-muted">
              <input type="checkbox" checked={structured} onChange={(event) => setStructured(event.target.checked)} />
              Gestructureerd antwoord
            </label>
            <button
              onClick={submit}
              disabled={busy || !first || !question.trim()}
              className="ml-auto flex items-center gap-1.5 rounded-md bg-live/85 px-3 py-1.5 font-medium text-white hover:bg-live disabled:opacity-40"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              {busy ? "Analyseren…" : "Uitvoeren"}
            </button>
          </div>
          {error && <p className="text-fault">{error}</p>}
        </section>

        {run && (
          <>
            <section className="flex flex-wrap gap-3">
              {run.images.map((image) => (
                <figure key={image.camera} className="w-72 max-w-full">
                  <img
                    src={`data:image/jpeg;base64,${image.jpeg}`}
                    alt={`Geanalyseerd beeld camera ${image.camera}`}
                    className="w-full rounded-md border border-line"
                  />
                  <figcaption className="mt-1 text-[12px] text-muted">Camera {image.camera}</figcaption>
                </figure>
              ))}
            </section>
            <section className={`grid gap-3 ${run.results.length > 1 ? "md:grid-cols-2" : ""}`}>
              {run.results.map((result) => (
                <Result key={result.model} result={result} />
              ))}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function Result({ result }: { result: PlaygroundResult }) {
  return (
    <article className="rounded-lg border border-line bg-surface p-3">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3 text-[13px]">
        <span className="font-medium">{result.model}</span>
        {result.duration_s !== undefined && <span className="text-muted tabular-nums">{result.duration_s.toFixed(1)} s</span>}
        {result.valid === true && <span className="text-done">Uitvoer geldig</span>}
        {result.valid === false && <span className="text-fault">Uitvoer ongeldig</span>}
        {result.truncated && <span className="text-doubt">Afgekapt</span>}
      </header>
      {result.error ? (
        <p className="text-fault">{result.error}</p>
      ) : (
        <pre className="whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed">{result.response}</pre>
      )}
    </article>
  );
}

function ModelSelect({
  state,
  value,
  onChange,
  optional,
}: {
  state: AppState;
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
}) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {optional && <option value="">Geen</option>}
      {state.models.map((model) => (
        <option key={model.name} value={model.name}>
          {model.name}
        </option>
      ))}
    </select>
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
