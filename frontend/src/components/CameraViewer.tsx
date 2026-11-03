import { AlertTriangle, Check, Crop, Crosshair, Layers, Maximize2, RotateCw, Trash2, VideoOff, X } from "lucide-react";
import { useRef, useState } from "react";
import { post, request, type Camera, type Roi, type Step } from "../api";

const MIN_SIZE = 0.05;

const AREAS = {
  roi: { path: "roi", hint: "Sleep een kader om het werkgebied." },
  count: { path: "count-area", hint: "Sleep een kader om de plek waar gedraaid wordt, bijvoorbeeld de schroef met de hand." },
};

const percent = (share: number | null) => (share === null ? "" : `${(share * 100).toFixed(1).replace(".", ",")}%`);

async function calibrate(slot: number) {
  if (!window.confirm("Het huidige beeld wordt de referentie voor deze camera. Staat de camera goed?")) return;
  const { error } = await request(`/api/cameras/${slot}/calibrate`, "POST");
  if (error) window.alert(error);
}

const box = (area: Roi) => ({
  left: `${area.x * 100}%`,
  top: `${area.y * 100}%`,
  width: `${area.w * 100}%`,
  height: `${area.h * 100}%`,
});

export default function CameraViewer({ camera, counting }: { camera: Camera; counting?: Step }) {
  const frame = useRef<HTMLDivElement>(null);
  const [editing, setEditing] = useState<keyof typeof AREAS | null>(null);
  const [draft, setDraft] = useState<Roi | null>(null);
  const [ghost, setGhost] = useState(false);
  const start = useRef<{ x: number; y: number } | null>(null);

  function position(event: React.PointerEvent) {
    const box = frame.current!.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)),
      y: Math.min(1, Math.max(0, (event.clientY - box.top) / box.height)),
    };
  }

  function onDown(event: React.PointerEvent) {
    event.currentTarget.setPointerCapture(event.pointerId);
    start.current = position(event);
    setDraft(null);
  }

  function onMove(event: React.PointerEvent) {
    if (!start.current) return;
    const now = position(event);
    setDraft({
      x: Math.min(start.current.x, now.x),
      y: Math.min(start.current.y, now.y),
      w: Math.abs(now.x - start.current.x),
      h: Math.abs(now.y - start.current.y),
    });
  }

  function close() {
    setEditing(null);
    setDraft(null);
    start.current = null;
  }

  async function save() {
    if (editing && draft && draft.w >= MIN_SIZE && draft.h >= MIN_SIZE) {
      await post(`/api/cameras/${camera.slot}/${AREAS[editing].path}`, draft);
    }
    close();
  }

  async function remove() {
    if (editing) await post(`/api/cameras/${camera.slot}/${AREAS[editing].path}`);
    close();
  }

  const shown = editing === "count" ? camera.roi : (draft ?? camera.roi);
  const countArea = editing === "count" ? (draft ?? camera.count_area) : camera.count_area;
  const existing = editing === "count" ? camera.count_area : camera.roi;

  return (
    <section ref={frame} className="group relative aspect-video overflow-hidden rounded-lg border border-line bg-black">
      {camera.connected ? (
        <img
          src={`/api/cameras/${camera.slot}/stream`}
          alt={`Live beeld ${camera.label}`}
          draggable={false}
          className="h-full w-full object-contain select-none"
        />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-muted">
          <VideoOff size={24} />
          <span>{camera.error}</span>
        </div>
      )}

      {ghost && camera.connected && camera.calibrated_at && (
        <img
          src={`/api/cameras/${camera.slot}/reference.jpg?${encodeURIComponent(camera.calibrated_at ?? "")}`}
          alt=""
          className="pointer-events-none absolute inset-0 h-full w-full object-contain opacity-45 mix-blend-screen"
        />
      )}

      {shown && camera.connected && (
        <div
          className="pointer-events-none absolute border-2 border-live shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]"
          style={box(shown)}
        />
      )}

      {countArea && camera.connected && (
        <div className="pointer-events-none absolute border-2 border-dashed border-white/90" style={box(countArea)}>
          <span className="absolute top-0 left-0 bg-black/75 px-1.5 py-0.5 text-[12px] whitespace-nowrap tabular-nums">
            {counting ? `${counting.turns} / ${counting.expected_turns} draaibewegingen` : "Telgebied"}
          </span>
        </div>
      )}

      {editing && (
        <div
          className="absolute inset-0 cursor-crosshair touch-none"
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={() => (start.current = null)}
        />
      )}

      {camera.connected &&
        !editing &&
        camera.detections?.boxes.map((found, index) => (
          <div key={index} className="pointer-events-none absolute border-2 border-live" style={box(found)}>
            <span className="absolute bottom-full left-[-2px] max-w-52 truncate bg-live px-1.5 py-0.5 text-[12px] text-white">
              {found.label}
            </span>
          </div>
        ))}
      {camera.connected && camera.workmat && (
        <span
          className={`pointer-events-none absolute bottom-2 left-2 flex max-w-[60%] items-center gap-1 rounded bg-black/75 px-1.5 py-0.5 text-[12px] ${
            camera.workmat.found ? "text-ink/85" : "text-doubt"
          }`}
        >
          {camera.workmat.found ? (
            "Werkmat gevonden: werkgebied automatisch"
          ) : (
            <>
              <AlertTriangle size={12} className="shrink-0" /> Werkmat niet in beeld
            </>
          )}
        </span>
      )}

      {camera.connected && !camera.workmat?.found && camera.calibration && camera.calibration.state !== "ok" && (
        <span
          className={`pointer-events-none absolute bottom-2 left-2 flex max-w-[60%] items-center gap-1 rounded bg-black/75 px-1.5 py-0.5 text-[12px] ${
            camera.calibration.state === "lost" ? "text-doubt" : "text-ink/85"
          }`}
        >
          {camera.calibration.state === "lost" ? (
            <>
              <AlertTriangle size={12} className="shrink-0" /> Camera verplaatst? Kalibreer opnieuw.
            </>
          ) : (
            `${percent(camera.calibration.shift)} verschoven, gebieden meebewogen`
          )}
        </span>
      )}

      {camera.connected && !editing && camera.detections && (
        <span className="pointer-events-none absolute right-2 bottom-2 rounded bg-black/70 px-1.5 py-0.5 text-[12px] text-ink/85 tabular-nums">
          {camera.detections.boxes.length === 0
            ? `Model zag om ${camera.detections.time} geen objecten`
            : `Vakken van het model, beeld van ${camera.detections.time}`}
        </span>
      )}

      <div className="absolute inset-x-0 top-0 flex items-center gap-2 bg-gradient-to-b from-black/70 to-transparent px-3 py-2 text-[13px]">
        <span className={`size-2 rounded-full ${camera.connected ? "bg-done" : "bg-fault"}`} />
        <span className="font-medium">
          Camera {camera.slot} — {camera.label}
        </span>
        {camera.connected && (
          <span className="ml-auto text-ink/75 tabular-nums">
            {camera.width}×{camera.height} · {camera.fps.toFixed(0)} FPS
          </span>
        )}
        <button
          aria-label={`Werkgebied ${camera.label} instellen`}
          title={camera.workmat?.found ? "Het werkgebied komt nu van de werkmat" : "Werkgebied instellen"}
          disabled={!camera.connected || !!camera.workmat?.found}
          className={`rounded p-1 text-ink/80 hover:bg-white/15 disabled:opacity-40 ${camera.connected ? "" : "ml-auto"}`}
          onClick={() => setEditing("roi")}
        >
          <Crop size={14} />
        </button>
        <button
          aria-label={`Telgebied ${camera.label} instellen`}
          title="Telgebied voor draaibewegingen"
          disabled={!camera.connected}
          className="rounded p-1 text-ink/80 hover:bg-white/15 disabled:opacity-40"
          onClick={() => setEditing("count")}
        >
          <RotateCw size={14} />
        </button>
        <button
          aria-label={`${camera.label} kalibreren`}
          title="Kalibreren: huidig beeld als referentie bewaren"
          disabled={!camera.connected}
          className="rounded p-1 text-ink/80 hover:bg-white/15 disabled:opacity-40"
          onClick={() => calibrate(camera.slot)}
        >
          <Crosshair size={14} />
        </button>
        {camera.calibrated_at && (
          <button
            aria-label={`Referentiebeeld ${camera.label} ${ghost ? "verbergen" : "tonen"}`}
            title="Referentiebeeld over het live beeld leggen, om de camera terug te zetten"
            aria-pressed={ghost}
            className={`rounded p-1 hover:bg-white/15 ${ghost ? "bg-white/20 text-ink" : "text-ink/80"}`}
            onClick={() => setGhost(!ghost)}
          >
            <Layers size={14} />
          </button>
        )}
        <button
          aria-label={`${camera.label} schermvullend`}
          title="Schermvullend"
          className="rounded p-1 text-ink/80 hover:bg-white/15"
          onClick={() => frame.current?.requestFullscreen()}
        >
          <Maximize2 size={14} />
        </button>
      </div>

      {editing && (
        <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-black/80 px-3 py-2 text-[13px]">
          <span className="min-w-0 flex-1 truncate text-ink/85">{AREAS[editing].hint}</span>
          <Tool onClick={save} disabled={!draft || draft.w < MIN_SIZE || draft.h < MIN_SIZE}>
            <Check size={13} /> Opslaan
          </Tool>
          {existing && (
            <Tool onClick={remove}>
              <Trash2 size={13} /> Verwijderen
            </Tool>
          )}
          <Tool onClick={close}>
            <X size={13} /> Annuleren
          </Tool>
        </div>
      )}
    </section>
  );
}

function Tool({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="flex shrink-0 items-center gap-1 rounded border border-white/25 px-2 py-0.5 hover:bg-white/15 disabled:opacity-40"
    >
      {children}
    </button>
  );
}
