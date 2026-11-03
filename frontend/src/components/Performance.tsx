import { useEffect, useState } from "react";
import { request, type AppState, type Camera } from "../api";
import LineChart from "./LineChart";

interface Report {
  analyses: { t: number; duration_s: number; gap_s: number | null; images: number; width: number }[];
  samples: { t: number; fps: Record<string, number> }[];
  stats: {
    total: number;
    skipped: number;
    failed: number;
    invalid: number;
    last_s: number | null;
    average_s: number | null;
    median_s: number | null;
    p95_s: number | null;
    per_minute: number | null;
  };
  system: { cpu_percent?: number | null; memory_mb?: number | null; model_memory_mb?: number | null };
  cameras: Camera[];
}

const SERIES_1 = "var(--color-series-1)";
const SERIES_2 = "var(--color-series-2)";

const number = (value: number | null | undefined, unit: string) =>
  value === null || value === undefined ? "—" : `${value.toFixed(1)} ${unit}`;

export default function Performance({ state }: { state: AppState }) {
  const [report, setReport] = useState<Report | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      const { data } = await request<Report>("/api/performance", "GET");
      if (active && data) setReport(data);
    }
    load();
    const timer = window.setInterval(load, 2000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  if (!report) return <main className="p-4 text-muted">Metingen laden…</main>;

  const { stats, system, analyses, samples } = report;
  const last = analyses[analyses.length - 1];

  return (
    <main className="min-h-0 flex-1 overflow-auto p-3">
      <div className="mx-auto flex max-w-6xl flex-col gap-3">
        <dl className="grid grid-cols-2 gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-4 lg:grid-cols-8">
          <Stat label="Laatste analyse" value={number(stats.last_s, "s")} />
          <Stat label="Gemiddeld" value={number(stats.average_s, "s")} />
          <Stat label="Mediaan" value={number(stats.median_s, "s")} />
          <Stat label="P95" value={number(stats.p95_s, "s")} />
          <Stat label="Per minuut" value={number(stats.per_minute, "")} />
          <Stat label="Analyses" value={String(stats.total)} />
          <Stat label="Overgeslagen" value={String(stats.skipped)} />
          <Stat label="Mislukt / ongeldig" value={`${stats.failed} / ${stats.invalid}`} />
        </dl>

        <div className="grid gap-3 lg:grid-cols-2">
          <LineChart
            title="Duur per analyse"
            unit="s"
            times={analyses.map((entry) => entry.t)}
            series={[{ name: "Duur", colour: SERIES_1, values: analyses.map((entry) => entry.duration_s) }]}
          />
          <LineChart
            title="Analyses per minuut"
            unit="per min"
            times={analyses.map((entry) => entry.t)}
            series={[
              {
                name: "Frequentie",
                colour: SERIES_1,
                values: analyses.map((entry) => (entry.gap_s ? 60 / entry.gap_s : null)),
              },
            ]}
          />
          <LineChart
            title="Camera-FPS"
            unit="FPS"
            times={samples.map((sample) => sample.t)}
            series={[
              { name: "Camera 1", colour: SERIES_1, values: samples.map((sample) => sample.fps["1"] ?? null) },
              { name: "Camera 2", colour: SERIES_2, values: samples.map((sample) => sample.fps["2"] ?? null) },
            ]}
          />

          <section className="rounded-lg border border-line bg-surface p-3">
            <h2 className="mb-2 font-medium">Huidige situatie</h2>
            <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-[13px]">
              <Row label="Actief model" value={state.settings.model ?? "—"} />
              <Row label="Minimale interval" value={`${state.settings.interval_s} s`} />
              <Row label="Beeldbreedte naar model" value={last ? `${last.width} px` : "—"} />
              <Row label="Beelden per analyse" value={last ? String(last.images) : "—"} />
              {report.cameras.map((camera) => (
                <Row
                  key={camera.slot}
                  label={`Camera ${camera.slot}`}
                  value={camera.connected ? `${camera.width}×${camera.height}, ${camera.fps.toFixed(0)} FPS` : "Niet verbonden"}
                />
              ))}
              <Row label="CPU van de app" value={number(system.cpu_percent, "%")} />
              <Row label="Geheugen van de app" value={number(system.memory_mb, "MB")} />
              <Row label="Geheugen geladen model" value={number(system.model_memory_mb, "MB")} />
            </dl>
            <p className="mt-3 text-[12px] text-muted">
              GPU-gebruik en temperatuur worden niet getoond: macOS biedt daar geen betrouwbare meting voor.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="mt-0.5 text-lg tabular-nums">{value}</dd>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className="text-right tabular-nums">{value}</dd>
    </>
  );
}
