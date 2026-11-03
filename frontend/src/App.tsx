import { AlertTriangle, FlaskConical, Images, ScanEye, WifiOff } from "lucide-react";
import { useState } from "react";
import { useAppState, type AppState } from "./api";
import ActivityLog from "./components/ActivityLog";
import AIPlayground from "./components/AIPlayground";
import CameraViewer from "./components/CameraViewer";
import DemoPanel from "./components/DemoPanel";
import Controls from "./components/Controls";
import Header, { type Page } from "./components/Header";
import ObservationPanel from "./components/ObservationPanel";
import Performance from "./components/Performance";
import SettingsPage from "./components/SettingsPage";
import SimulationPanel from "./components/SimulationPanel";
import WorkflowChecklist from "./components/WorkflowChecklist";
import WorkflowEditor from "./components/WorkflowEditor";

export default function App() {
  const { state, connected } = useAppState();
  const [page, setPage] = useState<Page>("dashboard");
  const [openWorkflow, setOpenWorkflow] = useState<string | null>(null);

  if (!state) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-muted">
        <ScanEye size={18} /> Verbinden met AssemblyVision…
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <Header state={state} page={page} onNavigate={setPage} />
      {state.simulated && (
        <div className="flex items-center justify-center gap-2 bg-doubt py-1.5 font-semibold tracking-wide text-black">
          <FlaskConical size={15} /> SIMULATIEMODUS — geen echte AI-analyse
        </div>
      )}
      {state.test_source && (
        <div className="flex items-center justify-center gap-2 bg-raised py-1.5 font-semibold tracking-wide text-doubt">
          <Images size={15} /> TESTBEELDEN — geen live camerabeeld
        </div>
      )}
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
      {page === "dashboard" && (
        <Dashboard
          state={state}
          onOpenWorkflow={(id) => {
            setOpenWorkflow(id);
            setPage("workflows");
          }}
        />
      )}
      {page === "workflows" && <WorkflowEditor state={state} openId={openWorkflow} />}
      {page === "playground" && <AIPlayground state={state} />}
      {page === "performance" && <Performance state={state} />}
      {page === "settings" && <SettingsPage state={state} />}
    </div>
  );
}

function Dashboard({ state, onOpenWorkflow }: { state: AppState; onOpenWorkflow: (id: string) => void }) {
  const counting = state.workflow.steps.find(
    (step) => step.expected_turns !== null && step.state !== "waiting" && step.state !== "completed",
  );

  return (
    <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-auto p-3 lg:grid-cols-[minmax(0,1fr)_370px] lg:overflow-hidden">
      <div className="flex min-h-0 flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {state.cameras.map((camera) => (
            <CameraViewer key={camera.slot} camera={camera} counting={counting} />
          ))}
        </div>
        <Controls state={state} />
        {state.demo && <DemoPanel state={state} onOpen={onOpenWorkflow} />}
        {state.simulated && <SimulationPanel />}
        <div className="grid min-h-[220px] flex-1 grid-cols-1 gap-3 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:min-h-0">
          <ObservationPanel observations={state.observations} />
          <ActivityLog log={state.log} />
        </div>
      </div>
      <WorkflowChecklist state={state} />
    </main>
  );
}

function Banner({ tone, children }: { tone: "fault" | "doubt"; children: React.ReactNode }) {
  const colour = tone === "fault" ? "text-fault border-fault/40" : "text-doubt border-doubt/40";
  return <div className={`flex items-center gap-2 border-b bg-surface px-4 py-2 ${colour}`}>{children}</div>;
}
