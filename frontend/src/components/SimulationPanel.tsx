import { post } from "../api";

const ACTIONS = [
  { kind: "valid", label: "Geldige observatie" },
  { kind: "incomplete", label: "Onvolledige observatie" },
  { kind: "uncertain", label: "Onzekerheid" },
  { kind: "wrong", label: "Verkeerde handeling" },
];

export default function SimulationPanel() {
  return (
    <section className="flex flex-wrap items-center gap-2 rounded-lg border border-doubt/40 bg-surface px-3 py-2">
      <span className="text-[13px] text-doubt">Simuleer:</span>
      {ACTIONS.map((action) => (
        <button
          key={action.kind}
          onClick={() => post("/api/simulation/observe", { name: action.kind })}
          className="rounded-md border border-line px-2.5 py-1 text-[13px] hover:bg-raised"
        >
          {action.label}
        </button>
      ))}
    </section>
  );
}
