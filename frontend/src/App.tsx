import { AlertTriangle, ScanEye, WifiOff } from "lucide-react";
import { useAppState } from "./api";
import ActivityLog from "./components/ActivityLog";
import CameraViewer from "./components/CameraViewer";
import Controls from "./components/Controls";
import Header from "./components/Header";
import ObservationPanel from "./components/ObservationPanel";
import WorkflowChecklist from "./components/WorkflowChecklist";

export default function App() {
  const { state, connected } = useAppState();

  if (!state) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-muted">
        <ScanEye size={18} /> Verbinden met AssemblyVision…
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Header state={state} />
      {!connected && (
        <Banner tone="fault">
          <WifiOff size={15} /> Verbinding met de backend verbroken. Opnieuw verbinden…
        </Banner>
      )}
      {state.message && (
        <Banner tone={state.monitoring === "error" ? "fault" : "doubt"}>
          <AlertTriangle size={15} /> {state.message}
        </Banner>
      )}
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-auto p-3 lg:grid-cols-[minmax(0,1fr)_370px] lg:overflow-hidden">
        <div className="flex min-h-0 flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {state.cameras.map((camera) => (
              <CameraViewer key={camera.slot} camera={camera} />
            ))}
          </div>
          <Controls state={state} />
          <div className="grid min-h-[220px] flex-1 grid-cols-1 gap-3 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:min-h-0">
            <ObservationPanel observations={state.observations} />
            <ActivityLog log={state.log} />
          </div>
        </div>
        <WorkflowChecklist state={state} />
      </main>
    </div>
  );
}

function Banner({ tone, children }: { tone: "fault" | "doubt"; children: React.ReactNode }) {
  const colour = tone === "fault" ? "text-fault border-fault/40" : "text-doubt border-doubt/40";
  return <div className={`flex items-center gap-2 border-b bg-surface px-4 py-2 ${colour}`}>{children}</div>;
}
