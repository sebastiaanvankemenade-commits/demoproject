import { Download, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { post, request, type AppState, type InferenceSettings } from "../api";

const PROFILES = { light: "Licht", power: "Krachtig" };

const gigabytes = (bytes: number | null) => (bytes === null ? "—" : `${(bytes / 1e9).toFixed(1)} GB`);

export default function SettingsPage({ state }: { state: AppState }) {
  const [inference, setInference] = useState<InferenceSettings>(state.settings.inference);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => setInference(state.settings.inference), [state.settings.inference]);

  async function save() {
    const { error } = await request("/api/settings", "POST", { inference });
    setNotice(error ? { text: error, error: true } : { text: "Opgeslagen.", error: false });
  }

  async function confirmed(question: string, path: string, done: string) {
    if (!window.confirm(question)) return;
    const { error } = await request(path, "POST");
    setNotice(error ? { text: error, error: true } : { text: done, error: false });
  }

  const set = <K extends keyof InferenceSettings>(key: K, value: InferenceSettings[K]) =>
    setInference({ ...inference, [key]: value });

  return (
    <main className="min-h-0 flex-1 overflow-auto p-3">
      <div className="mx-auto flex max-w-4xl flex-col gap-3">
        <Section title="Apparaat" hint="Het profiel zet startwaarden en bepaalt welke modellen te kiezen zijn. Elke waarde blijft daarna aan te passen.">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[13px]">
            <dt className="text-muted">Gevonden</dt>
            <dd>
              {state.device.name}
              {state.device.memory_gb !== null && ` · ${state.device.memory_gb} GB geheugen`}
            </dd>
            <dt className="text-muted">Grootste model</dt>
            <dd>{state.device.model_limit_gb === null ? "Onbekend" : `${state.device.model_limit_gb} GB`}</dd>
          </dl>
          <Field label="Profiel" hint="Licht: één camera per ronde vakken, kleine modellen. Krachtig: alle camera's, hogere beeldbreedte, alle modellen die passen.">
            <select
              value={state.settings.device_profile}
              className="w-fit"
              onChange={(e) => post("/api/device-profile", { name: e.target.value })}
            >
              <option value="auto">Automatisch ({PROFILES[state.device.recommended]})</option>
              <option value="light">Licht</option>
              <option value="power">Krachtig</option>
            </select>
          </Field>
        </Section>

        <Section
          title="Werkmat"
          hint="Print de werkmat en leg hem onder het werk. Elke camera vindt de mat zelf, ook na opnieuw opbouwen, en zet het werkgebied eromheen. Het telgebied schuift mee."
        >
          <div className="flex flex-wrap items-center gap-4">
            <a
              href="/api/workmat.png"
              className="flex w-fit items-center gap-1 rounded-md border border-line px-2.5 py-1 text-[13px] text-muted hover:text-ink"
            >
              <Download size={13} /> Werkmat downloaden
            </a>
            <label className="flex items-center gap-1.5 text-[13px] text-muted">
              <input
                type="checkbox"
                checked={state.settings.auto_work_area}
                onChange={(e) => post("/api/settings", { auto_work_area: e.target.checked })}
              />
              Werkgebied automatisch van de werkmat
            </label>
          </div>
          <p className="text-[12px] text-muted">
            Op elk formaat te printen, A4 of groter. Houd de vier hoekmarkers vrij; één afgedekte marker mag.
          </p>
        </Section>

        <Section title="AI-instellingen" hint="Deze gelden voor nieuwe analyses. De standaardwaarden voor Licht zijn getest op de MacBook Air.">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Beeldbreedte naar het model" hint="Op de Air gaf dit nauwelijks verschil in snelheid.">
              <select value={inference.image_width} onChange={(e) => set("image_width", Number(e.target.value) as InferenceSettings["image_width"])}>
                {[384, 512, 768, 1024].map((width) => (
                  <option key={width} value={width}>
                    {width} px
                  </option>
                ))}
              </select>
            </Field>
            <NumberField label="Temperatuur" hint="0 geeft het meest voorspelbare antwoord." value={inference.temperature} step={0.1} onChange={(v) => set("temperature", v)} />
            <NumberField label="Contextlengte" hint="Hoger gebruikt meer geheugen. Twee beelden passen ruim in 8192." value={inference.num_ctx} step={1024} onChange={(v) => set("num_ctx", v)} />
            <NumberField label="Maximale antwoordlengte (tokens)" hint="Afgekapte antwoorden tellen nooit als bewijs." value={inference.num_predict} step={50} onChange={(v) => set("num_predict", v)} />
            <NumberField label="Time-out (seconden)" hint="Daarna telt de analyse als mislukt." value={inference.timeout_s} step={10} onChange={(v) => set("timeout_s", v)} />
            <Field label="Model geladen houden" hint="Bijvoorbeeld 10m of 1h.">
              <input value={inference.keep_alive} onChange={(e) => set("keep_alive", e.target.value)} className={INPUT} />
            </Field>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button onClick={save} className="rounded-md bg-live/85 px-3 py-1.5 font-medium text-white hover:bg-live">
              Opslaan
            </button>
            {notice && <span className={`text-[13px] ${notice.error ? "text-fault" : "text-done"}`}>{notice.text}</span>}
          </div>
        </Section>

        <Section title="Geïnstalleerde vision-modellen">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead className="text-left text-[12px] text-muted">
                <tr>
                  <th className="py-1 pr-3 font-normal">Model</th>
                  <th className="pr-3 font-normal">Familie</th>
                  <th className="pr-3 font-normal">Parameters</th>
                  <th className="pr-3 font-normal">Kwantisatie</th>
                  <th className="pr-3 font-normal">Grootte</th>
                  <th className="font-normal">Past op dit apparaat</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {state.models.map((model) => (
                  <tr key={model.name} className="border-t border-line/60">
                    <td className="py-1 pr-3">
                      {model.name}
                      {model.name === state.settings.model && <span className="ml-2 text-live">actief</span>}
                    </td>
                    <td className="pr-3">{model.family ?? "—"}</td>
                    <td className="pr-3">{model.parameter_size ?? "—"}</td>
                    <td className="pr-3">{model.quantization ?? "—"}</td>
                    <td className="pr-3">{gigabytes(model.size)}</td>
                    <td className={model.fits ? "" : "text-doubt"}>{model.fits ? "Ja" : "Te groot"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {state.models.length === 0 && <p className="text-muted">Geen vision-modellen gevonden in Ollama.</p>}
          <Secondary onClick={() => post("/api/models/refresh")}>
            <RefreshCw size={13} /> Modellen vernieuwen
          </Secondary>
        </Section>

        <Section title="Camera's">
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-[13px]">
            {state.cameras.map((camera) => (
              <div key={camera.slot} className="contents">
                <dt className="text-muted">{camera.label}</dt>
                <dd>{camera.serial ?? "Geen camera toegewezen"}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section title="Lokale gegevens" hint="Alles blijft op deze computer. Beelden worden alleen bewaard als je zelf een testopname maakt.">
          <div className="flex flex-wrap gap-2">
            <a
              href="/api/data/events.csv"
              className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1 text-[13px] text-muted hover:text-ink"
            >
              <Download size={13} /> Activiteit exporteren
            </a>
            <Secondary onClick={() => confirmed("Alle activiteit wissen?", "/api/data/clear-events", "Activiteit gewist.")}>
              Activiteit wissen
            </Secondary>
            <Secondary onClick={() => confirmed("Alle testopnames verwijderen?", "/api/data/delete-snapshots", "Testopnames verwijderd.")}>
              Testopnames verwijderen
            </Secondary>
            <Secondary
              onClick={() =>
                confirmed(
                  "Voorkeuren en werkgebieden terugzetten? De cameratoewijzing blijft staan.",
                  "/api/data/reset-preferences",
                  "Voorkeuren teruggezet.",
                )
              }
            >
              Voorkeuren terugzetten
            </Secondary>
          </div>
        </Section>
      </div>
    </main>
  );
}

const INPUT = "rounded-md border border-line bg-raised px-2.5 py-1 text-[14px] text-ink";

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4">
      <div>
        <h2 className="font-medium">{title}</h2>
        {hint && <p className="text-[13px] text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[12px] text-muted">
      {label}
      {children}
      <span>{hint}</span>
    </label>
  );
}

function NumberField({
  label,
  hint,
  value,
  step,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <input type="number" step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className={INPUT} />
    </Field>
  );
}

function Secondary({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="flex w-fit items-center gap-1 rounded-md border border-line px-2.5 py-1 text-[13px] text-muted hover:text-ink"
    >
      {children}
    </button>
  );
}
