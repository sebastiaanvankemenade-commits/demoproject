import type { ObservationEntry } from "../api";

const STATUS = {
  completed: { text: "Criterium lijkt voldaan", colour: "text-done" },
  incomplete: { text: "Criterium niet voldaan", colour: "text-ink" },
  uncertain: { text: "Onzeker", colour: "text-doubt" },
};

export default function ObservationPanel({ observations }: { observations: ObservationEntry[] }) {
  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
      <h2 className="border-b border-line px-3 py-2 font-medium">AI-observaties</h2>
      <div className="min-h-0 flex-1 overflow-auto">
        {observations.length === 0 && <p className="p-3 text-muted">Nog geen analyses uitgevoerd.</p>}
        {observations.map((entry, index) => (
          <Entry key={`${entry.time}-${index}`} entry={entry} />
        ))}
      </div>
    </section>
  );
}

function Entry({ entry }: { entry: ObservationEntry }) {
  const status = STATUS[entry.status];
  const cameras = entry.cameras.map((camera) => `camera ${camera}`).join(" + ");
  const seen = [...entry.visible_objects, ...entry.relationships].join(", ");

  return (
    <article className="border-b border-line/60 px-3 py-2 text-[13px] last:border-0">
      <div className="mb-1 text-[12px] text-muted tabular-nums">
        {entry.time} · {cameras}
        {!entry.model && " · beeldcontrole"}
      </div>
      {seen && <Row label="Gezien">{seen}</Row>}
      <Row label="Model">
        <span className={status.colour}>{status.text}:</span> {entry.evidence}
      </Row>
      <Row label="Besluit">{entry.decision.join(" ")}</Row>
    </article>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[52px_minmax(0,1fr)] gap-2 leading-snug">
      <span className="text-[12px] text-muted">{label}</span>
      <span>{children}</span>
    </div>
  );
}
