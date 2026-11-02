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
}

export interface Camera {
  slot: number;
  label: string;
  connected: boolean;
  fps: number;
  width: number;
  height: number;
  serial: string | null;
  error: string | null;
}

export interface ObservationEntry {
  time: string;
  cameras: number[];
  model: string | null;
  visible_objects: string[];
  relationships: string[];
  evidence: string;
  status: "completed" | "incomplete" | "uncertain";
  decision: string[];
}

export interface AppState {
  ollama_connected: boolean;
  models: { name: string; parameter_size: string | null; quantization: string | null }[];
  monitoring: "idle" | "running" | "analyzing" | "error";
  message: string | null;
  settings: { model: string | null; camera_mode: "both" | "1" | "2"; interval_s: number; image_width: number };
  cameras: Camera[];
  workflows: { id: string; name: string }[];
  workflow: { id: string; name: string; steps: Step[] };
  progress: number;
  observations: ObservationEntry[];
  log: { time: string; text: string }[];
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
