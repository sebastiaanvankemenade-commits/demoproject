import { useEffect, useState } from "react";

export type StepState =
  | "waiting"
  | "active"
  | "analyzing"
  | "verifying"
  | "completed"
  | "uncertain"
  | "deviation";

export interface Step {
  id: string;
  number: number;
  title: string;
  instruction: string;
  state: StepState;
  confirmations: number;
  required: number;
  method: "ai" | "simulated" | "manual" | null;
  confirmed_at: string | null;
  warning: string | null;
  turns: number;
  expected_turns: number | null;
}

export interface Roi {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Detection {
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Camera {
  slot: number;
  label: string;
  connected: boolean;
  fps: number;
  width: number;
  height: number;
  serial: string | null;
  roi: Roi | null;
  count_area: Roi | null;
  detections: { time: string; boxes: Detection[] } | null;
  calibrated_at: string | null;
  workmat: { found: boolean; markers: number } | null;
  calibration: { state: "ok" | "corrected" | "lost"; shift: number | null } | null;
  error: string | null;
}

export interface WorkflowStepDefinition {
  id: string;
  title: string;
  instruction: string;
  completion_criterion: string;
  expected_objects: string[];
  deviation_conditions: string[];
  required_confirmations: number | null;
  requires_transition: boolean;
  expected_turns: number | null;
}

export interface WorkflowDefinition {
  schema_version: number;
  id: string;
  name: string;
  required_confirmations: number;
  steps: WorkflowStepDefinition[];
}

export interface PlaygroundResult {
  model: string;
  response?: string;
  duration_s?: number;
  valid?: boolean | null;
  truncated?: boolean;
  error?: string;
}

export interface PlaygroundRun {
  question: string;
  images: { camera: number; jpeg: string }[];
  results: PlaygroundResult[];
}

export interface ObservationEntry {
  time: string;
  cameras: number[];
  model: string | null;
  simulated: boolean;
  visible_objects: string[];
  relationships: string[];
  evidence: string;
  status: "completed" | "incomplete" | "uncertain";
  decision: string[];
}

export interface InferenceSettings {
  image_width: 384 | 512 | 768 | 1024;
  temperature: number;
  num_ctx: number;
  num_predict: number;
  timeout_s: number;
  keep_alive: string;
}

export interface AppState {
  ollama_connected: boolean;
  models: {
    name: string;
    size: number | null;
    family: string | null;
    parameter_size: string | null;
    quantization: string | null;
    fits: boolean;
  }[];
  device: {
    name: string;
    memory_gb: number | null;
    model_budget_gb: number | null;
    recommended: "light" | "power";
    profile: "light" | "power";
    model_limit_gb: number | null;
  };
  monitoring: "idle" | "running" | "analyzing" | "error";
  message: string | null;
  simulated: boolean;
  switching_model: boolean;
  test_source: { scene: string | null; scenes: string[] } | null;
  settings: { model: string | null; camera_mode: "both" | "1" | "2"; interval_s: number; show_boxes: boolean; boxes_all_cameras: boolean; device_profile: "auto" | "light" | "power"; auto_work_area: boolean; inference: InferenceSettings };
  cameras: Camera[];
  workflows: { id: string; name: string }[];
  workflow: { id: string; name: string; steps: Step[] };
  progress: number;
  observations: ObservationEntry[];
  log: { time: string; text: string }[];
  demo: {
    name: string;
    parts: string[];
    state: "recording" | "generating" | "done" | "failed";
    auto: boolean;
    moving: boolean;
    steps: { time: string; note: string | null; turns: number; auto: boolean; pictures: number; seconds: number }[];
    progress: number;
    workflow_id: string | null;
    failed: number[];
  } | null;
  metrics: {
    last_s: number | null;
    average_s: number | null;
    actual_interval_s: number | null;
    total: number;
    failed: number;
    invalid: number;
  };
}

export async function post(path: string, body?: unknown): Promise<void> {
  await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** For calls whose outcome the operator must see. Returns the Dutch error from the backend. */
export async function request<T>(path: string, method: string, body?: unknown): Promise<{ data?: T; error?: string }> {
  try {
    const response = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const payload = await response.json().catch(() => null);
    if (response.ok) return { data: payload as T };
    const detail = payload?.detail;
    return { error: typeof detail === "string" ? detail : "De invoer is ongeldig. Controleer de velden." };
  } catch {
    return { error: "Geen verbinding met de backend." };
  }
}

export function useAppState(): { state: AppState | null; connected: boolean } {
  const [state, setState] = useState<AppState | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;

    function connect() {
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${location.host}/ws`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = (message) => setState(JSON.parse(message.data));
      socket.onclose = () => {
        setConnected(false);
        if (!closed) retry = window.setTimeout(connect, 1500);
      };
    }

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      socket?.close();
    };
  }, []);

  return { state, connected };
}
