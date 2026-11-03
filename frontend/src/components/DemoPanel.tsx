import { Check, Hand, ListPlus, Loader2, X } from "lucide-react";
import { useState } from "react";
import { post, request, type AppState } from "../api";

export default function DemoPanel({ state, onOpen }: { state: AppState; onOpen: (id: string) => void }) {
  const demo = state.demo!;
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function call(path: string, body?: unknown) {
    const { error } = await request(path, "POST", body);
    setError(error ?? null);
    return !error;
  }

  async function mark() {
    if (await call("/api/demo/step", { note })) setNote("");
  }

  return (
    <section className="rounded-lg border border-live/50 bg-surface px-3 py-2.5">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
        <h2 className="font-medium">Voordoen: {demo.name}</h2>
        {demo.state === "recording" && (
          <>
            <span className={`flex items-center gap-1 text-[13px] ${demo.moving ? "text-live" : "text-muted"}`}>
              <Hand size={13} /> {demo.moving ? "Beweging gezien: stap loopt" : "Wacht op de volgende handeling"}
            </span>
            <label className="ml-auto flex items-center gap-1.5 text-[13px] text-muted">
              <input type="checkbox" checked={demo.auto} onChange={(e) => call("/api/demo/options", { auto: e.target.checked })} />
              Stappen automatisch herkennen
            </label>
          </>
        )}
      </div>
      {demo.state === "recording" && (
        <p className="mb-2 text-[13px] text-muted">
          {demo.auto
            ? "Doe de stappen gewoon voor. Na een paar seconden stilstand legt de app de stap vast. Typ daarna kort wat je deed."
            : "Doe een stap voor, beschrijf hem kort en leg hem vast."}
          {!state.cameras.some((camera) => camera.count_area) && " Wordt er gedraaid? Teken eerst een telgebied, dan telt de app mee."}
        </p>
      )}

      <ol className="mb-2 flex gap-2 overflow-x-auto pb-1">
        {[{ time: "begin", note: "Beginsituatie", turns: 0 }, ...demo.steps].map((step, index) => (
          <li key={index} className="w-36 shrink-0 text-[12px]">
            {demo.state === "recording" ? (
              <img src={`/api/demo/${index}.jpg?${demo.steps.length}`} alt="" className="aspect-video w-full rounded border border-line object-cover" />
            ) : (
              <div className="aspect-video w-full rounded border border-line bg-raised" />
            )}
            <div className="mt-1 truncate text-muted tabular-nums">
              {index === 0 ? "Begin" : `Stap ${index}${"auto" in step && step.auto ? " · automatisch" : ""}`}
            </div>
            {index > 0 && demo.state === "recording" ? (
              <input
                defaultValue={step.note ?? ""}
                maxLength={120}
                placeholder="Wat deed je?"
                aria-label={`Notitie stap ${index}`}
                onBlur={(event) => call("/api/demo/options", { step: index - 1, note: event.target.value })}
                className="mt-0.5 w-full rounded border border-line bg-raised px-1.5 py-0.5 text-[12px] text-ink"
              />
            ) : (
              index > 0 && step.note && <div className="truncate">{step.note}</div>
            )}
            {step.turns > 0 && <div className="text-muted tabular-nums">{step.turns} draaibewegingen</div>}
          </li>
        ))}
      </ol>

      {demo.state === "recording" && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-[12px] text-muted">
            Zelf een stap afsluiten, met wat je deed (aanbevolen)
            <input
              value={note}
              maxLength={120}
              placeholder="Bijvoorbeeld: shaft op de barrel draaien"
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && mark()}
              className="rounded-md border border-line bg-raised px-2.5 py-1.5 text-[14px] text-ink"
            />
          </label>
          <button onClick={mark} className="flex items-center gap-1.5 rounded-md bg-live/85 px-3 py-1.5 font-medium text-white hover:bg-live">
            <ListPlus size={14} /> Stap vastleggen
          </button>
          <Plain disabled={demo.steps.length === 0} onClick={() => call("/api/demo/finish")}>
            <Check size={14} /> Klaar: instructies maken
          </Plain>
          <Plain onClick={() => call("/api/demo/cancel")}>
            <X size={14} /> Annuleren
          </Plain>
        </div>
      )}

      {demo.state === "generating" && (
        <p className="flex items-center gap-2 text-[13px]">
          <Loader2 size={14} className="animate-spin text-live" />
          Het model bekijkt stap {demo.progress} van {demo.steps.length}. Op deze computer kan dat per stap een à twee minuten duren.
        </p>
      )}

      {demo.state === "done" && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-done">Werkinstructie gemaakt, nog niet actief.</span>
          {demo.failed.length > 0 && (
            <span className="text-doubt">
              {demo.failed.length === 1 ? `Stap ${demo.failed[0]} is` : `Stappen ${demo.failed.join(", ")} zijn`} niet herkend: vul
              die zelf in.
            </span>
          )}
          <button
            onClick={() => {
              onOpen(demo.workflow_id!);
              post("/api/demo/cancel");
            }}
            className="rounded-md bg-live/85 px-3 py-1.5 font-medium text-white hover:bg-live"
          >
            Nakijken in de editor
          </button>
          <Plain onClick={() => call("/api/demo/cancel")}>Sluiten</Plain>
        </div>
      )}

      {demo.state === "failed" && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-fault">Het model gaf geen antwoord. Er is niets opgeslagen.</span>
          <Plain onClick={() => call("/api/demo/cancel")}>Sluiten</Plain>
        </div>
      )}

      {error && <p className="mt-2 text-[13px] text-fault">{error}</p>}
    </section>
  );
}

function Plain({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-muted hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  );
}
