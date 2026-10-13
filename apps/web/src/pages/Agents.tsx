import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, uid } from "../api/client";
import type { Run, TreeNode } from "../api/types";
import { useProject } from "../App";
import { Icon } from "../components/Icon";
import { Card, Empty, Field, Modal, Status, Tabs, useToast } from "../components/ui";
import { ago } from "../lib/arabic";

export function AgentsPage() {
  const { pid } = useParams();
  const proj = useProject();
  const can = proj.data?.permissions?.includes("run_agents");
  const cat = useQuery<any>({ queryKey: ["catalog"], queryFn: () => api("/v1/agents/catalog") });
  const runs = useQuery<{ items: Run[] }>({
    queryKey: ["runs", pid], queryFn: () => api(`/v1/projects/${pid}/runs`),
    refetchInterval: (q) => (q.state.data?.items.some((r) => ["queued", "running"].includes(r.status)) ? 1500 : false),
  });
  const [launch, setLaunch] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  if (!cat.data) return null;
  const skills = Object.fromEntries(cat.data.skills.map((s: any) => [s.id, s]));
  return (
    <>
      <div className="page-head">
        <div className="grow"><div className="eyebrow">عمليات الوكلاء</div><h1>غرفة الوكلاء</h1>
          <div className="muted">ثلاثة عشر دوراً بعشرين مهارة وأكثر. كل وكيل يقرأ مشروعك فقط ويُصدر مقترحات؛ لا يملك أي وكيل حق القبول أو تعديل الكانون أو الحذف أو النشر.</div></div>
        {can && <button className="btn gold" onClick={() => setLaunch("A00")}><Icon name="play" size={16} /> تشغيل رئيس التحرير (فحص شامل)</button>}
      </div>

      <div className={`alert ${cat.data.provider.available ? (cat.data.provider.external ? "warn" : "info") : "info"}`} style={{ marginBottom: 16 }}>
        <strong>مزود النماذج:</strong> {cat.data.provider.destination} — {cat.data.provider.message}
        {cat.data.provider.retention_note && <div className="dim">{cat.data.provider.retention_note}</div>}
      </div>

      <Card title="سلسلة التسليم (A00)" icon="agents" className="" bodyClass="card-b">
        <Pipeline pipeline={cat.data.pipeline} agents={cat.data.agents} />
        <div className="row" style={{ marginTop: 8 }}>
          <span className="dim">الأدوات المسموحة:</span>{cat.data.tools.allowed.map((t: string) => <span key={t} className="badge ok mono">{t}</span>)}
          <span className="dim">محظورة على كل الوكلاء:</span>{cat.data.tools.forbidden.map((t: string) => <span key={t} className="badge bad mono">{t}</span>)}
        </div>
      </Card>

      <div className="grid g3" style={{ marginTop: 16 }}>
        {cat.data.agents.filter((a: any) => a.id !== "A00").map((a: any) => (
          <div key={a.id} className="card">
            <div className="card-b stack" style={{ gap: 6 }}>
              <div className="row between"><span className="row"><span className="badge info mono">{a.id}</span><strong>{a.name}</strong></span>
                {can && <button className="btn sm" onClick={() => setLaunch(a.id)}><Icon name="play" size={12} /> تشغيل</button>}</div>
              <div className="dim">{a.role}</div>
              <div className="pill-list">{a.skills.map((s: string) => (
                <span key={s} className={`badge ${skills[s].mode === "model" ? "warn" : skills[s].mode === "hybrid" ? "gold" : ""}`} title={skills[s].mode === "model" ? "يتطلب مزوداً" : skills[s].mode === "hybrid" ? "حتمي + إثراء نموذجي اختياري" : "حتمي يعمل بلا نموذج"}>
                  {s} · {skills[s].name}</span>))}</div>
            </div>
          </div>
        ))}
      </div>

      <Card title="سجل التشغيل" icon="history" className="" bodyClass="card-b" >
        {!runs.data?.items.length ? <Empty title="لا تشغيلات بعد" /> : (
          <table className="table"><thead><tr><th>الوكيل</th><th>المهارات</th><th>الحالة</th><th>المخاطرة</th><th>المزود</th><th>الرموز</th><th>متى</th><th /></tr></thead>
            <tbody>{runs.data.items.map((r) => (
              <tr key={r.id} className="clickable" onClick={() => setOpen(r.id)}>
                <td><span className="mono">{r.agent_id}</span> {r.agent_name}</td><td className="mono dim">{r.skills.join(" ")}</td>
                <td><Status value={r.status} /></td><td><span className="badge">{r.risk_level}</span></td>
                <td className="mono">{r.provider === "disabled" ? "حتمي" : r.model_id}</td><td className="mono">{r.tokens_used}</td>
                <td className="dim">{ago(r.created_at)}</td><td><Icon name="search" size={14} /></td>
              </tr>))}
            </tbody></table>
        )}
      </Card>
      {launch && <LaunchModal agentId={launch} catalog={cat.data} onClose={() => setLaunch(null)} onStarted={(id) => { setLaunch(null); setOpen(id); }} />}
      {open && <RunModal runId={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function Pipeline({ pipeline, agents }: { pipeline: string[][]; agents: any[] }) {
  const name = (id: string) => agents.find((a) => a.id === id)?.name || id;
  const W = 980, colW = W / (pipeline.length + 1), H = 150;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="سلسلة تسليم الوكلاء">
      <g>
        <rect x={W - colW + 10} y={H / 2 - 20} width={colW - 30} height={40} rx={8} fill="var(--primary)" />
        <text x={W - colW / 2 - 5} y={H / 2 + 5} textAnchor="middle" style={{ fill: "var(--on-primary)", fontSize: 12 }}>A00 رئيس التحرير</text>
      </g>
      {pipeline.map((stage, i) => {
        const cx = W - colW * (i + 1.5);
        const gap = Math.min(28, (H - 10) / stage.length);
        return (
          <g key={i}>
            <line x1={cx + colW / 2 - 8} x2={cx + colW / 2 - 22} y1={H / 2} y2={H / 2} stroke="var(--gold)" strokeWidth={2} markerEnd="url(#arr)" />
            {stage.map((a, j) => {
              const y = H / 2 + (j - (stage.length - 1) / 2) * gap;
              return (
                <g key={a}>
                  <rect x={cx - colW / 2 + 12} y={y - 11} width={colW - 30} height={22} rx={5} fill="var(--panel-3)" stroke="var(--line-strong)" />
                  <text x={cx - 3} y={y + 4} textAnchor="middle" style={{ fill: "var(--text)", fontSize: 10.5 }}>{a} {name(a).split(" ").slice(0, 2).join(" ")}</text>
                </g>
              );
            })}
          </g>
        );
      })}
      <defs><marker id="arr" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M10 0L0 5l10 5z" fill="var(--gold)" /></marker></defs>
    </svg>
  );
}

function LaunchModal({ agentId, catalog, onClose, onStarted }: { agentId: string; catalog: any; onClose: () => void; onStarted: (id: string) => void }) {
  const { pid } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const agent = catalog.agents.find((a: any) => a.id === agentId);
  const tree = useQuery<any>({ queryKey: ["tree", pid], queryFn: () => api(`/v1/projects/${pid}/tree`) });
  const chapters: TreeNode[] = (tree.data?.manuscripts?.[0]?.nodes || []).filter((n: TreeNode) => n.type === "chapter");
  const allSkills: string[] = agentId === "A00" ? catalog.skills.map((s: any) => s.id) : agent.skills;
  const [skills, setSkills] = useState<string[]>(allSkills);
  const [goal, setGoal] = useState("");
  const [scope, setScope] = useState<string[]>([]);
  const [useModel, setUseModel] = useState(false);
  const [ack, setAck] = useState(false);
  const [high, setHigh] = useState(false);
  const key = useMemo(() => uid(), []); // stable per dialog → double-clicks/retries never duplicate (AT20)
  const p = catalog.provider;
  const m = useMutation({
    mutationFn: () => api<Run>("/v1/agents/runs", { body: {
      project_id: pid, agent_id: agentId, skills, goal, node_ids: scope, idempotency_key: key,
      use_model: useModel, acknowledge_external: ack, confirm_high_risk: high } }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["runs", pid] }); qc.invalidateQueries({ queryKey: ["dashboard", pid] }); onStarted(r.id); },
    onError: (e) => {
      if (e instanceof ApiError && e.type === "/problems/consent-required") toast.info("امنح موافقة نقل البيانات من «الإعدادات والخصوصية» أولاً.");
      toast.error(e);
    },
  });
  return (
    <Modal title={`تشغيل ${agent.id} — ${agent.name}`} wide onClose={onClose}
      footer={<><span className="dim">مفتاح عدم التكرار: <span className="mono">{key.slice(0, 8)}</span></span><span style={{ flex: 1 }} />
        <button className="btn" onClick={onClose}>إلغاء</button><button className="btn primary" disabled={!skills.length || m.isPending} onClick={() => m.mutate()}><Icon name="play" size={14} /> تشغيل</button></>}>
      <div className="stack">
        <Field label="الهدف (اختياري)"><input className="input" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="مثلاً: مراجعة الفصلين الأولين قبل إرسالهما للمحرر" /></Field>
        <Field label="المهارات">
          <div className="pill-list">{allSkills.map((s) => {
            const on = skills.includes(s);
            const sk = catalog.skills.find((x: any) => x.id === s);
            return <button type="button" key={s} className={`btn sm ${on ? "gold" : ""}`} onClick={() => setSkills(on ? skills.filter((x) => x !== s) : [...skills, s])}>{s} {sk.name}</button>;
          })}</div>
        </Field>
        <Field label="النطاق (اتركه فارغاً لكامل المخطوط)">
          <div className="pill-list">{chapters.map((c) => {
            const on = scope.includes(c.id);
            return <button type="button" key={c.id} className={`btn sm ${on ? "gold" : ""}`} onClick={() => setScope(on ? scope.filter((x) => x !== c.id) : [...scope, c.id])}>{c.label}</button>;
          })}</div>
        </Field>
        <label className="check"><input type="checkbox" checked={useModel} disabled={!p.available} onChange={(e) => setUseModel(e.target.checked)} />
          استخدم مزود النماذج للمهارات الهجينة/التوليدية {p.available ? `(${p.destination})` : "— غير متاح؛ سيعمل التحليل الحتمي فقط"}</label>
        {useModel && p.external && (
          <div className="alert warn">
            سيُرسل جزء من نص المخطوط إلى <strong>{p.destination}</strong>. {p.retention_note}
            <label className="check" style={{ marginTop: 6 }}><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> أعلم بوجهة البيانات وأوافق على هذا الإرسال.</label>
            <label className="check"><input type="checkbox" checked={high} onChange={(e) => setHigh(e.target.checked)} /> تأكيد منفصل: هذا تشغيل عالي المخاطرة.</label>
          </div>
        )}
        <div className="alert info">لن يتغير أي نص: المخرجات تقرير منفصل + مقترحات تنتظر قرارك في غرفة النقد.</div>
      </div>
    </Modal>
  );
}

function RunModal({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { pid } = useParams();
  const toast = useToast();
  const q = useQuery<Run>({
    queryKey: ["run", runId], queryFn: () => api(`/v1/agents/runs/${runId}`),
    refetchInterval: (qq) => (qq.state.data && ["queued", "running"].includes(qq.state.data.status) ? 1200 : false),
  });
  const [tab, setTab] = useState<"steps" | "report" | "metrics">("steps");
  const r = q.data;
  if (!r) return null;
  const report = r.output?.report;
  const cancel = async () => { try { await api(`/v1/agents/runs/${runId}/cancel`, { method: "POST" }); q.refetch(); } catch (e) { toast.error(e); } };
  const proposals = r.steps.reduce((a: number, s: any) => a + (s.proposals || 0), 0);
  return (
    <Modal title={<span className="row"><span className="mono">{r.agent_id}</span> {r.agent_name} <Status value={r.status} /></span>} wide onClose={onClose}
      footer={<>{["queued", "running"].includes(r.status) && <button className="btn danger" onClick={cancel}><Icon name="stop" size={14} /> إلغاء</button>}
        <span style={{ flex: 1 }} />{proposals > 0 && <Link className="btn gold" to={`/p/${pid}/proposals`}>مراجعة {proposals} مقترحاً</Link>}</>}>
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="badge">المخاطرة {r.risk_level}</span><span className="badge mono">{r.provider === "disabled" ? "deterministic" : r.model_id}</span>
        <span className="badge mono">tokens {r.tokens_used}</span>{r.output?.cost_note && <span className="dim">{r.output.cost_note}</span>}
      </div>
      {r.error && <div className="alert bad">{r.error}</div>}
      <Tabs value={tab} onChange={setTab} items={[["steps", "الخطوات"], ["report", "التقرير التحريري"], ["metrics", "القياسات"]]} />
      {tab === "steps" && (
        <table className="table"><tbody>{r.steps.map((s: any, i: number) => (
          <tr key={i}><td className="mono">{s.agent}:{s.skill}</td><td><Status value={s.status === "done" ? "succeeded" : s.status === "pending" ? "queued" : s.status} /></td>
            <td>{s.summary}<div className="dim">{s.note}</div></td><td className="mono">{s.findings ?? ""}</td><td className="mono">{s.proposals ? `+${s.proposals}` : ""}</td></tr>))}
        </tbody></table>
      )}
      {tab === "report" && (!report ? <Empty title="يظهر التقرير بعد اكتمال التشغيل" /> : (
        <div className="stack">
          <div className="alert info">{report.disclaimer}</div>
          {Object.entries(report.sections).map(([area, b]: [string, any]) => (
            <Card key={area} title={area}>
              <div className="grid g2">
                <div><div className="dim" style={{ marginBottom: 4 }}>موضوعي — قابل للتحقق</div>
                  {b.objective.map((f: any, i: number) => <div key={i} className="evidence" style={{ marginBottom: 4 }}><Status value={f.certainty} /> {f.claim}</div>)}
                  {!b.objective.length && <span className="dim">—</span>}</div>
                <div><div className="dim" style={{ marginBottom: 4 }}>ذوقي — اقتراح نقدي</div>
                  {b.taste.map((f: any, i: number) => <div key={i} className="evidence" style={{ marginBottom: 4 }}><Status value={f.certainty} /> {f.claim}</div>)}
                  {!b.taste.length && <span className="dim">—</span>}</div>
              </div>
            </Card>
          ))}
          {Object.values(r.output?.results || {}).flatMap((x: any) => x.warnings).filter(Boolean).map((w: string, i: number) => <div key={i} className="alert warn">{w}</div>)}
        </div>
      ))}
      {tab === "metrics" && <pre className="mono" style={{ whiteSpace: "pre-wrap", maxHeight: 420, overflow: "auto", textAlign: "left" }}>
        {JSON.stringify(Object.fromEntries(Object.entries(r.output?.results || {}).map(([k, v]: any) => [k, v.metrics])), null, 1)}</pre>}
    </Modal>
  );
}
