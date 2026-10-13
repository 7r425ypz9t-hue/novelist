/* Hand-built SVG charts: zero dependencies, theme-aware via CSS variables, RTL-aware axes. */
import { useMemo, useState } from "react";
import { fmt } from "../lib/arabic";

export function BarChart({ data, height = 180, gold = false }: { data: { label: string; value: number }[]; height?: number; gold?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return <div className="empty">لا بيانات بعد</div>;
  const max = Math.max(...data.map((d) => d.value), 1);
  const w = 600, pad = 24, bw = (w - pad * 2) / data.length;
  return (
    <svg className="chart" viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img" aria-label="مخطط أعمدة">
      <line className="axis" x1={pad} x2={w - pad} y1={height - 22} y2={height - 22} />
      {data.map((d, i) => {
        // RTL: first item on the right
        const x = w - pad - (i + 1) * bw + bw * 0.15;
        const h = ((height - 40) * d.value) / max;
        return (
          <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect className={`bar ${gold ? "gold" : ""}`} x={x} y={height - 22 - h} width={bw * 0.7} height={Math.max(h, 1)} rx={3}
              opacity={hover === null || hover === i ? 1 : 0.45} />
            {data.length <= 16 && <text x={x + bw * 0.35} y={height - 6} textAnchor="middle">{d.label.length > 10 ? d.label.slice(0, 9) + "…" : d.label}</text>}
            {hover === i && <text x={x + bw * 0.35} y={height - 28 - h} textAnchor="middle" style={{ fill: "var(--text)" }}>{fmt(d.value)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

export function AreaChart({ data, height = 140 }: { data: { label: string; value: number }[]; height?: number }) {
  const path = useMemo(() => {
    if (data.length < 2) return null;
    const w = 600, max = Math.max(...data.map((d) => d.value), 1);
    const pts = data.map((d, i) => [w - (i / (data.length - 1)) * w, height - 18 - ((height - 30) * d.value) / max]);
    const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("");
    return { line, area: `${line}L0,${height - 18}L${w},${height - 18}Z` };
  }, [data, height]);
  if (!path) return <div className="empty">يظهر منحنى الكتابة اليومية بعد يومين من النشاط.</div>;
  return (
    <svg className="chart" viewBox={`0 0 600 ${height}`} width="100%" height={height} role="img" aria-label="منحنى الكلمات اليومية">
      <path className="area" d={path.area} />
      <path className="line" d={path.line} />
      <text x={596} y={height - 4} textAnchor="end">{data[0].label}</text>
      <text x={4} y={height - 4}>{data[data.length - 1].label}</text>
    </svg>
  );
}

export function Donut({ parts, size = 120 }: { parts: { value: number; color: string; label: string }[]; size?: number }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  const r = size / 2 - 10, c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="row" style={{ gap: 16 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="توزيع">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--panel-3)" strokeWidth={12} />
        {total > 0 && parts.map((p, i) => {
          const len = (p.value / total) * c;
          const el = <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={p.color} strokeWidth={12}
            strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-acc} transform={`rotate(-90 ${size / 2} ${size / 2})`} />;
          acc += len;
          return el;
        })}
        <text x="50%" y="52%" textAnchor="middle" style={{ fill: "var(--text)", fontSize: 20, fontFamily: "var(--font-mono)" }}>{total}</text>
      </svg>
      <div className="legend" style={{ flexDirection: "column" }}>
        {parts.map((p) => <span key={p.label}><i style={{ background: p.color }} />{p.label}: <span className="num">{p.value}</span></span>)}
      </div>
    </div>
  );
}

export function LineSeries({ series, height = 160, labels }: {
  series: { name: string; color: string; values: number[] }[]; height?: number; labels: string[];
}) {
  const n = labels.length;
  if (n < 2) return <div className="empty">تحتاج وحدتين سرديتين على الأقل.</div>;
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const w = 600;
  const x = (i: number) => w - 10 - (i / (n - 1)) * (w - 20);
  const y = (v: number) => height - 20 - ((height - 34) * v) / max;
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img" aria-label="منحنيات">
        <line className="axis" x1={10} x2={w - 10} y1={height - 20} y2={height - 20} />
        {series.map((s) => (
          <path key={s.name} d={s.values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("")} fill="none" stroke={s.color} strokeWidth={2} />
        ))}
        {n <= 14 && labels.map((l, i) => <text key={i} x={x(i)} y={height - 5} textAnchor="middle">{l.length > 8 ? l.slice(-8) : l}</text>)}
      </svg>
      <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
    </div>
  );
}
