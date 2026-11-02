import { Maximize2, VideoOff } from "lucide-react";
import { useRef } from "react";
import type { Camera } from "../api";

export default function CameraViewer({ camera }: { camera: Camera }) {
  const frame = useRef<HTMLDivElement>(null);

  return (
    <section ref={frame} className="group relative aspect-video overflow-hidden rounded-lg border border-line bg-black">
      {camera.connected ? (
        <img
          src={`/api/cameras/${camera.slot}/stream`}
          alt={`Live beeld ${camera.label}`}
          className="h-full w-full object-contain"
        />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-muted">
          <VideoOff size={24} />
          <span>{camera.error}</span>
        </div>
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
          aria-label={`${camera.label} schermvullend`}
          className={`rounded p-1 text-ink/80 hover:bg-white/15 ${camera.connected ? "" : "ml-auto"}`}
          onClick={() => frame.current?.requestFullscreen()}
        >
          <Maximize2 size={14} />
        </button>
      </div>
    </section>
  );
}
