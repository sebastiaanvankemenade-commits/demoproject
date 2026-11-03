import { Activity, Camera, Cpu, FlaskConical, LayoutDashboard, ListChecks, Radio, ScanEye, Settings } from "lucide-react";
import type { AppState } from "../api";

export type Page = "dashboard" | "workflows" | "playground" | "performance" | "settings";

const PAGES: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard size={14} /> },
  { id: "workflows", label: "Werkinstructies", icon: <ListChecks size={14} /> },
  { id: "playground", label: "AI Playground", icon: <FlaskConical size={14} /> },
  { id: "performance", label: "Prestaties", icon: <Activity size={14} /> },
  { id: "settings", label: "Instellingen", icon: <Settings size={14} /> },
];

const MONITORING = {
  idle: { text: "Gestopt", colour: "text-muted" },
  running: { text: "Monitoring actief", colour: "text-live" },
  analyzing: { text: "Analyseren", colour: "text-live" },
  error: { text: "Probleem", colour: "text-fault" },
};

interface Props {
  state: AppState;
  page: Page;
  onNavigate: (page: Page) => void;
}

export default function Header({ state, page, onNavigate }: Props) {
  const cameras = state.cameras.filter((camera) => camera.connected).length;
  const monitoring = MONITORING[state.monitoring];

  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line bg-surface px-4 py-2">
      <div className="flex items-center gap-2 font-semibold tracking-tight">
        <ScanEye size={19} className="text-live" /> AssemblyVision
      </div>
      <nav className="flex gap-1">
        {PAGES.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            aria-current={page === item.id ? "page" : undefined}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] ${
              page === item.id ? "bg-raised text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {item.icon} {item.label}
          </button>
        ))}
      </nav>
      <div className="min-w-0 flex-1 truncate text-[13px] text-muted">{state.workflow.name}</div>
      <Indicator colour={state.ollama_connected ? "text-done" : "text-fault"} icon={<Cpu size={14} />}>
        {state.ollama_connected ? state.settings.model ?? "Geen vision-model" : "Ollama niet bereikbaar"}
      </Indicator>
      <Indicator colour={cameras === 2 ? "text-done" : "text-doubt"} icon={<Camera size={14} />}>
        {cameras} van 2 camera's
      </Indicator>
      <Indicator colour={monitoring.colour} icon={<Radio size={14} />}>
        {monitoring.text}
      </Indicator>
    </header>
  );
}

function Indicator({ colour, icon, children }: { colour: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 text-[13px]">
      <span className={colour}>{icon}</span>
      <span className="text-ink/85">{children}</span>
    </div>
  );
}
