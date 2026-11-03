import { useRef, useState } from "react";

export interface Series {
  name: string;
  /** CSS colour. Validated for the dark surface; status colours stay reserved. */
  colour: string;
  values: (number | null)[];
}

interface Props {
  title: string;
  unit: string;
  times: number[];
  series: Series[];
}

const WIDTH = 640;
const HEIGHT = 190;
const PAD = { left: 38, right: 72, top: 12, bottom: 22 };

const clock = (seconds: number) => new Date(seconds * 1000).toLocaleTimeString("nl-NL");

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= value)!;
  return step * magnitude;
}

export default function LineChart({ title, unit, times, series }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const defined = series.flatMap((line) => line.values.filter((value): value is number => value !== null));
  const count = times.length;

  if (defined.length === 0) {
    return (
      <Frame title={title} series={series}>
        <p className="py-14 text-center text-muted">Nog geen metingen.</p>
      </Frame>
    );
  }

  const top = niceMax(Math.max(...defined));
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (index: number) => PAD.left + (count > 1 ? (index / (count - 1)) * plotWidth : plotWidth / 2);
  const y = (value: number) => PAD.top + plotHeight - (value / top) * plotHeight;

  function path(values: (number | null)[]): string {
    let drawing = false;
    return values
      .map((value, index) => {
        if (value === null) {
          drawing = false;
          return "";
        }
        const command = drawing ? "L" : "M";
        drawing = true;
        return `${command}${x(index).toFixed(1)} ${y(value).toFixed(1)}`;
      })
      .join(" ");
  }

  function track(event: React.PointerEvent) {
    const box = svg.current!.getBoundingClientRect();
    const position = ((event.clientX - box.left) / box.width) * WIDTH;
    setHover(Math.max(0, Math.min(count - 1, Math.round(((position - PAD.left) / plotWidth) * (count - 1)))));
  }

  const format = (value: number | null) => (value === null ? "—" : `${value.toFixed(1)} ${unit}`);

  /** Lines that end close together would otherwise print their labels on top of each other. */
  function labelOffset(index: number): number {
    const ends = series.map((line) => y(line.values.findLast((value) => value !== null) ?? 0));
    if (ends.length !== 2 || Math.abs(ends[0] - ends[1]) >= 13) return 0;
    return ends[index] < ends[1 - index] || index === 0 ? -7 : 7;
  }

  return (
    <Frame title={title} series={series}>
      <div className="relative">
        <svg
          ref={svg}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full touch-none"
          role="img"
          aria-label={title}
          onPointerMove={track}
          onPointerLeave={() => setHover(null)}
        >
          {[0, top / 2, top].map((tick) => (
            <g key={tick}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} stroke="var(--color-line)" strokeWidth={1} />
              <text x={PAD.left - 6} y={y(tick) + 4} textAnchor="end" fontSize={11} fill="var(--color-muted)">
                {tick % 1 === 0 ? tick : tick.toFixed(1)}
              </text>
            </g>
          ))}
          <text x={PAD.left} y={HEIGHT - 5} fontSize={11} fill="var(--color-muted)">
            {clock(times[0])}
          </text>
          <text x={WIDTH - PAD.right} y={HEIGHT - 5} textAnchor="end" fontSize={11} fill="var(--color-muted)">
            {clock(times[count - 1])}
          </text>
          {series.map((line) => (
            <path
              key={line.name}
              d={path(line.values)}
              fill="none"
              stroke={line.colour}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {series.map((line, index) => {
            const last = line.values.findLastIndex((value) => value !== null);
            if (last < 0) return null;
            const end = y(line.values[last]!);
            return (
              <g key={line.name}>
                <circle cx={x(last)} cy={end} r={4} fill={line.colour} stroke="var(--color-surface)" strokeWidth={2} />
                {series.length > 1 && (
                  <text x={x(last) + 8} y={end + 4 + labelOffset(index)} fontSize={11} fill="var(--color-ink)">
                    {line.name}
                  </text>
                )}
              </g>
            );
          })}
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotHeight} stroke="var(--color-muted)" strokeWidth={1} />
          )}
        </svg>
        {hover !== null && (
          <div
            className="pointer-events-none absolute top-1 rounded-md border border-line bg-raised px-2 py-1 text-[12px] shadow-lg"
            style={x(hover) > WIDTH / 2 ? { right: `${100 - (x(hover) / WIDTH) * 100 + 1}%` } : { left: `${(x(hover) / WIDTH) * 100 + 1}%` }}
          >
            <div className="text-muted tabular-nums">{clock(times[hover])}</div>
            {series.map((line) => (
              <div key={line.name} className="flex items-center gap-1.5 tabular-nums">
                <span className="h-0.5 w-3 rounded" style={{ background: line.colour }} />
                <strong className="font-medium">{format(line.values[hover])}</strong>
                {series.length > 1 && <span className="text-muted">{line.name}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
      <details className="mt-1 text-[12px] text-muted">
        <summary className="cursor-pointer">Tabel</summary>
        <table className="mt-1 w-full tabular-nums">
          <thead>
            <tr>
              <th className="text-left font-normal">Tijd</th>
              {series.map((line) => (
                <th key={line.name} className="text-right font-normal">
                  {line.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-ink">
            {times
              .map((time, index) => ({ time, index }))
              .slice(-10)
              .reverse()
              .map(({ time, index }) => (
                <tr key={`${time}-${index}`}>
                  <td>{clock(time)}</td>
                  {series.map((line) => (
                    <td key={line.name} className="text-right">
                      {format(line.values[index])}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </details>
    </Frame>
  );
}

function Frame({ title, series, children }: { title: string; series: Series[]; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-medium">{title}</h2>
        {series.length > 1 && (
          <ul className="flex gap-3 text-[12px] text-muted">
            {series.map((line) => (
              <li key={line.name} className="flex items-center gap-1.5">
                <span className="h-0.5 w-3 rounded" style={{ background: line.colour }} />
                {line.name}
              </li>
            ))}
          </ul>
        )}
      </div>
      {children}
    </section>
  );
}
