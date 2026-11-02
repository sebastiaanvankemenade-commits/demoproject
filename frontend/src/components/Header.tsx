import { Camera, Cpu, Radio, ScanEye } from "lucide-react";
import type { AppState } from "../api";

const MONITORING = {
  idle: { text: "Gestopt", colour: "text-muted" },
  running: { text: "Monitoring actief", colour: "text-live" },
  analyzing: { text: "Analyseren", colour: "text-live" },
  error: { text: "Probleem", colour: "text-fault" },
};

export default function Header({ state }: { state: AppState }) {
  const cameras = state.cameras.filter((camera) => camera.connected).length;
  const monitoring = MONITORING[state.monitoring];

  return (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line bg-surface px-4 py-2.5">
      <div className="flex items-center gap-2 font-semibold tracking-tight">
        <ScanEye size={19} className="text-live" /> AssemblyVision
      </div>
      <div className="min-w-0 flex-1 truncate text-muted">{state.workflow.name}</div>
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
