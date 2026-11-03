import { AlertTriangle, Check, CircleDashed, HelpCircle, Loader2, RotateCcw } from "lucide-react";
import { post, type AppState, type Step, type StepState } from "../api";

const STATES: Record<StepState, { label: string; colour: string }> = {
  waiting: { label: "Wachten", colour: "text-muted" },
  active: { label: "Actief", colour: "text-live" },
  analyzing: { label: "Analyseren", colour: "text-live" },
  verifying: { label: "Controleren", colour: "text-doubt" },
  completed: { label: "Voltooid", colour: "text-done" },
  uncertain: { label: "Onzeker", colour: "text-doubt" },
  deviation: { label: "Afwijking gedetecteerd", colour: "text-fault" },
};

const CONFIRMED = {
  ai: "Visueel bevestigd",
  manual: "Handmatig bevestigd",
  simulated: "Gesimuleerd bevestigd",
};

export default function WorkflowChecklist({ state }: { state: AppState }) {
  const active = state.workflow.steps.find((step) => step.state !== "completed" && step.state !== "waiting");

  return (
    <aside className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
      <div className="border-b border-line px-4 py-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-medium">Werkinstructie</h2>
          <span className="tabular-nums text-muted">{state.progress}%</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised">
          <div className="h-full rounded-full bg-done transition-[width] duration-300" style={{ width: `${state.progress}%` }} />
        </div>
      </div>

      <ol className="min-h-0 flex-1 overflow-auto p-2">
        {state.workflow.steps.map((step) => (
          <StepRow key={step.id} step={step} hasCountArea={state.cameras.some((camera) => camera.count_area)} />
        ))}
      </ol>

      <div className="flex flex-wrap gap-2 border-t border-line p-3">
        <Action disabled={!active} onClick={() => post("/api/step/confirm")}>
          Handmatig bevestigen
        </Action>
        <Action disabled={!active} onClick={() => post("/api/step/reject")}>
          Afwijzen
        </Action>
        <Action disabled={!active} onClick={() => post("/api/step/reset")}>
          Stap resetten
        </Action>
        <Action onClick={() => post("/api/workflow/restart")}>
          <RotateCcw size={13} /> Opnieuw beginnen
        </Action>
      </div>
    </aside>
  );
}

function StepRow({ step, hasCountArea }: { step: Step; hasCountArea: boolean }) {
  const state = STATES[step.state];
  const current = step.state !== "waiting" && step.state !== "completed";

  return (
    <li className={`flex gap-3 rounded-md px-2 py-2.5 ${current ? "bg-raised" : ""}`}>
      <div className={`mt-0.5 ${state.colour}`}>
        <StepIcon state={step.state} number={step.number} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className={`font-medium ${step.state === "waiting" ? "text-muted" : ""}`}>{step.title}</h3>
          <span className={`shrink-0 text-[12px] ${state.colour}`}>{state.label}</span>
        </div>
        <p className="mt-0.5 text-[13px] leading-snug text-muted">{step.instruction}</p>
        {step.expected_turns !== null && step.state !== "waiting" && (
          <p className="mt-1 text-[12px] tabular-nums">
            <span className={step.state === "completed" && step.turns < step.expected_turns ? "text-doubt" : "text-ink"}>
              {step.turns} van {step.expected_turns} draaibewegingen geteld
            </span>
            {current && !hasCountArea && (
              <span className="block text-doubt">Teken een telgebied op een camera om te tellen.</span>
            )}
          </p>
        )}
        {step.state === "verifying" && (
          <p className="mt-1 text-[12px] text-doubt tabular-nums">
            Bevestiging {step.confirmations} van {step.required}
          </p>
        )}
        {step.confirmed_at && (
          <p className="mt-1 text-[12px] text-done tabular-nums">
            {CONFIRMED[step.method ?? "ai"]} om {step.confirmed_at}
          </p>
        )}
        {step.warning && <p className="mt-1 text-[12px] text-fault">{step.warning}</p>}
      </div>
    </li>
  );
}

function StepIcon({ state, number }: { state: StepState; number: number }) {
  switch (state) {
    case "completed":
      return <Check size={18} className="step-confirmed" />;
    case "analyzing":
      return <Loader2 size={18} className="animate-spin" />;
    case "uncertain":
      return <HelpCircle size={18} />;
    case "deviation":
      return <AlertTriangle size={18} />;
    case "verifying":
      return <CircleDashed size={18} />;
    default:
      return <span className="flex size-[18px] items-center justify-center text-[13px] tabular-nums">{number}</span>;
  }
}

function Action({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[12px] text-muted hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  );
}
