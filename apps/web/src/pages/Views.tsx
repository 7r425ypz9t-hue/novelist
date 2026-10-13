import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { Card, Empty, Loading } from "../components/ui";

/* Story time (vertical, ↓ later) vs narration order (horizontal, → RTL first-to-last). Flashbacks show as upward jumps. */
export function TimelinePage() {
  const { pid } = useParams();
  const q = useQuery<any>({ queryKey: ["timeline", pid], queryFn: () => api(`/v1/projects/${pid}/timeline`) });
  const [hover, setHover] = useState<string | null>(null);
  const data = useMemo(() => {
    if (!q.data) return null;
    const pts = [
      ...q.data.scenes.filter((s: any) => s.story_time !== null).map((s: any) => ({ id: s.node_id, x: s.narration_index, y: s.story_time, label: s.label, kind: "scene" })),
    ];
    const events = q.data.events.filter((e: any) => e.story_time_start !== null);
    return { pts, events, untimedScenes: q.data.scenes.filter((s: any) => s.type === "scene" && s.story_time === null).length };
  }, [q.data]);
  if (!data) return <Loading />;
  const allY = [...data.pts.map((p: any) => p.y), ...data.events.flatMap((e: any) => [e.story_time_start, e.story_time_end ?? e.story_time_start])];
  const W = 900, H = 420, padX = 130, padY = 30;
  const minY = Math.min(...allY), maxY = Math.max(...allY);
  const maxX = Math.max(1, ...data.pts.map((p: any) => p.x), ...(q.data.scenes.map((s: any) => s.narration_index)));
  const sx = (x: number) => W - padX - ((x - 1) / Math.max(1, maxX - 1)) * (W - padX * 2);
  const sy = (y: number) => padY + ((y - minY) / Math.max(1e-9, maxY - minY || 1)) * (H - padY * 2);
  return (
    <>
      <div className="page-head"><div className="grow"><div className="eyebrow">محور الزمن</div><h1>الخط الزمني: زمن القصة مقابل ترتيب السرد</h1>
        <div className="muted">النقاط مشاهد بحسب موقعها في السرد (من اليمين) وزمنها في القصة (إلى الأسفل). القفزة إلى الأعلى استرجاع.</div></div></div>
      <div className="grid g3">
        <Card title="المخطط" className="span2" icon="timeline">
          {!allY.length ? <Empty title="لا أزمنة بعد">أضف «زمن القصة» في مصفوفة المشاهد أو تواريخ للأحداث.</Empty> : (
            <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="مخطط زمني">
              <line className="axis" x1={padX} x2={W - padX} y1={H - padY + 10} y2={H - padY + 10} />
              <line className="axis" x1={W - padX + 10} x2={W - padX + 10} y1={padY} y2={H - padY} />
              <text x={W - padX + 14} y={padY} textAnchor="start">{minY}</text>
              <text x={W - padX + 14} y={H - padY} textAnchor="start">{maxY}</text>
              <text x={W / 2} y={H - 4} textAnchor="middle">ترتيب السرد ←</text>
              {data.events.map((e: any) => (
                <g key={e.id} onMouseEnter={() => setHover(e.title)} onMouseLeave={() => setHover(null)}>
                  <rect x={padX - 8} y={sy(e.story_time_start) - 3} width={W - padX * 2 + 16} height={Math.max(6, sy(e.story_time_end ?? e.story_time_start) - sy(e.story_time_start) + 6)}
                    fill="var(--gold-soft)" opacity={0.6} />
                  <text x={padX - 12} y={sy(e.story_time_start) + 4} textAnchor="end" style={{ fill: "var(--gold)" }}>{e.title.length > 18 ? e.title.slice(0, 17) + "…" : e.title}</text>
                </g>
              ))}
              <path d={data.pts.map((p: any, i: number) => `${i ? "L" : "M"}${sx(p.x)},${sy(p.y)}`).join("")} fill="none" stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="4 4" />
              {data.pts.map((p: any, i: number) => {
                const back = i > 0 && p.y < data.pts[i - 1].y;
                return (
                  <g key={p.id} onMouseEnter={() => setHover(`${p.label} · ${p.y}`)} onMouseLeave={() => setHover(null)}>
                    <circle cx={sx(p.x)} cy={sy(p.y)} r={6} fill={back ? "var(--bad)" : "var(--accent)"} stroke="var(--panel)" strokeWidth={2} />
                  </g>
                );
              })}
              {hover && <text x={W / 2} y={18} textAnchor="middle" style={{ fill: "var(--text)", fontSize: 13 }}>{hover}</text>}
            </svg>
          )}
          <div className="legend"><span><i style={{ background: "var(--accent)" }} />مشهد</span><span><i style={{ background: "var(--bad)" }} />استرجاع (عودة في الزمن)</span><span><i style={{ background: "var(--gold)" }} />حدث في الكتاب المرجعي</span></div>
        </Card>
        <Card title="الأحداث بترتيب زمن القصة" icon="bible">
          <div className="stack scroll-y" style={{ gap: 6 }}>
            {[...q.data.events].sort((a: any, b: any) => (a.story_time_start ?? 1e9) - (b.story_time_start ?? 1e9)).map((e: any) => (
              <div key={e.id} className="row between"><span>{e.title}</span><span className="mono">{e.story_time_start ?? "؟"}</span></div>
            ))}
            {data.untimedScenes > 0 && <div className="alert warn">{data.untimedScenes} وحدة سردية بلا زمن قصة — لا تظهر في المخطط.</div>}
            <Link className="btn sm" to={`/p/${pid}/bible`}>إدارة الأحداث</Link>
          </div>
        </Card>
      </div>
    </>
  );
}

/* Force-directed relation graph (deterministic layout; no external lib). */
export function GraphPage() {
  const { pid } = useParams();
  const q = useQuery<any>({ queryKey: ["graph", pid], queryFn: () => api(`/v1/projects/${pid}/graph`) });
  const [sel, setSel] = useState<string | null>(null);
  const layout = useMemo(() => {
    if (!q.data) return null;
    const W = 900, H = 520;
    const nodes = q.data.nodes.map((n: any, i: number) => {
      const a = (i / Math.max(1, q.data.nodes.length)) * Math.PI * 2;
      return { ...n, x: W / 2 + Math.cos(a) * 180, y: H / 2 + Math.sin(a) * 180, vx: 0, vy: 0 };
    });
    const idx = new Map(nodes.map((n: any, i: number) => [n.id, i]));
    const edges = q.data.edges.filter((e: any) => idx.has(e.from) && idx.has(e.to));
    for (let it = 0; it < 220; it++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01, f = 2600 / d2;
        a.vx += dx * f / 60; a.vy += dy * f / 60; b.vx -= dx * f / 60; b.vy -= dy * f / 60;
      }
      for (const e of edges) {
        const a = nodes[idx.get(e.from) as number], b = nodes[idx.get(e.to) as number];
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, f = (d - 140) * 0.01;
        a.vx += (dx / d) * f; a.vy += (dy / d) * f; b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
      }
      for (const n of nodes) {
        n.vx += (W / 2 - n.x) * 0.002; n.vy += (H / 2 - n.y) * 0.002;
        n.x = Math.max(40, Math.min(W - 40, n.x + n.vx)); n.y = Math.max(30, Math.min(H - 30, n.y + n.vy));
        n.vx *= 0.6; n.vy *= 0.6;
      }
    }
    return { nodes, edges, idx, W, H };
  }, [q.data]);
  if (!layout) return <Loading />;
  const { nodes, edges, idx, W, H } = layout;
  const selEdges = sel ? edges.filter((e: any) => e.from === sel || e.to === sel) : [];
  return (
    <>
      <div className="page-head"><div className="grow"><div className="eyebrow">خريطة المعرفة</div><h1>شبكة العلاقات</h1>
        <div className="muted">الحواف من علاقات الكتاب المرجعي والأحداث المشتركة. انقر عقدة لرؤية روابطها وأدلتها.</div></div></div>
      <div className="grid g3">
        <Card title="الشبكة" className="span2" icon="graph">
          {!nodes.length ? <Empty title="لا كيانات بعد" /> : (
            <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="شبكة العلاقات">
              {edges.map((e: any) => {
                const a = nodes[idx.get(e.from) as number], b = nodes[idx.get(e.to) as number];
                const on = !sel || e.from === sel || e.to === sel;
                return <line key={e.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.status === "canon" ? "var(--p-coral)" : "var(--line-strong)"}
                  strokeWidth={on ? 1.6 : 0.6} opacity={on ? 1 : 0.25} strokeDasharray={e.status === "hypothesis" ? "4 4" : undefined} />;
              })}
              {nodes.map((n: any) => (
                <g key={n.id} onClick={() => setSel(sel === n.id ? null : n.id)} style={{ cursor: "pointer" }}>
                  <circle cx={n.x} cy={n.y} r={n.type === "character" ? 13 : 10} fill={n.type === "character" ? "var(--p-teal)" : "var(--p-salmon)"}
                    stroke={sel === n.id ? "var(--gold)" : "var(--accent)"} strokeWidth={sel === n.id ? 3 : 1.5} />
                  <text x={n.x} y={n.y + 26} textAnchor="middle" style={{ fill: "var(--text)", fontSize: 12 }}>{n.label}</text>
                </g>
              ))}
            </svg>
          )}
          <div className="legend"><span><i style={{ background: "var(--p-teal)" }} />شخصية</span><span><i style={{ background: "var(--p-salmon)" }} />مكان</span><span><i style={{ background: "var(--p-coral)" }} />علاقة معتمدة</span></div>
        </Card>
        <Card title={sel ? `روابط: ${nodes.find((n: any) => n.id === sel)?.label}` : "الروابط"} icon="link">
          {!sel ? <Empty title="اختر عقدة" /> : !selEdges.length ? <Empty title="لا روابط" /> : (
            <div className="stack" style={{ gap: 6 }}>{selEdges.map((e: any) => {
              const other = nodes[idx.get(e.from === sel ? e.to : e.from) as number];
              return <div key={e.id} className="evidence"><strong>{e.label}</strong> ↔ {other.label}<div className="dim">{e.status === "event" ? "مشاركة في حدث" : e.status}</div></div>;
            })}</div>
          )}
        </Card>
      </div>
    </>
  );
}
