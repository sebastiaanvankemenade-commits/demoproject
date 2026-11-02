import type { AppState } from "../api";

export default function ActivityLog({ log }: { log: AppState["log"] }) {
  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-line bg-surface">
      <h2 className="border-b border-line px-3 py-2 font-medium">Activiteit</h2>
      <ul className="min-h-0 flex-1 overflow-auto px-3 py-2 text-[13px]">
        {log.length === 0 && <li className="text-muted">Nog geen activiteit.</li>}
        {log.map((entry, index) => (
          <li key={`${entry.time}-${index}`} className="flex gap-2 py-0.5 leading-snug">
            <span className="shrink-0 text-muted tabular-nums">{entry.time}</span>
            <span>{entry.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
