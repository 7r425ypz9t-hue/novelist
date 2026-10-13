import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Proposal } from "../api/types";
import { useProject } from "../App";
import { Card, DiffView, Empty, EvidenceList, Field, Loading, Status, Tabs, useToast } from "../components/ui";
import { ago } from "../lib/arabic";

export function ProposalsPage() {
  const { pid } = useParams();
  const [state, setState] = useState<"pending" | "accepted" | "rejected" | "stale" | "all">("pending");
  const q = useQuery<{ items: Proposal[] }>({ queryKey: ["proposals", pid, state], queryFn: () => api(`/v1/projects/${pid}/proposals?state=${state}`) });
  const [sel, setSel] = useState<string | null>(null);
  const items = q.data?.items || [];
  const current = sel || items[0]?.id || null;
  return (
    <>
      <div className="page-head">
        <div className="grow"><div className="eyebrow">غرفة النقد</div><h1>المقترحات والنقد</h1>
          <div className="muted">كل مقترح موسوم بأصله (الوكيل/المهارة) ونسخة الأساس ودرجة اليقين. القبول يُنشئ مراجعة جديدة؛ الرفض لا يغيّر شيئاً.</div></div>
      </div>
      <Tabs value={state} onChange={(s) => { setState(s); setSel(null); }} items={[["pending", "معلقة"], ["accepted", "مقبولة"], ["rejected", "مرفوضة"], ["stale", "متقادمة"], ["all", "الكل"]]} />
      {q.isLoading ? <Loading /> : !items.length ? <Card><Empty title="لا مقترحات في هذا العرض">شغّل وكيلاً من غرفة الوكلاء لتوليد مقترحات.</Empty></Card> : (
        <div className="grid" style={{ gridTemplateColumns: "minmax(260px, 360px) 1fr" }}>
          <Card title={`${items.length} مقترحاً`} bodyClass="">
            <div className="scroll-y" style={{ maxHeight: "70vh" }}>
              {items.map((p) => (
                <button key={p.id} onClick={() => setSel(p.id)} className="tree-node" style={{ width: "100%", border: 0, background: current === p.id ? "var(--accent-soft)" : "none", textAlign: "right", font: "inherit", display: "block", borderBottom: "1px solid var(--line)", borderRadius: 0, padding: "10px 12px" }}>
                  <div className="row between"><span className="mono">{p.agent_id}/{p.skill_id}</span><Status value={p.state} /></div>
                  <div style={{ color: "var(--text)" }}>{p.title}</div>
                  <div className="row"><Status value={p.certainty} /><span className="badge">{p.kind === "patch" ? "تعديل نص" : p.kind === "fact" ? "حقيقة" : "ملاحظة"}</span><span className="dim">{ago(p.created_at)}</span></div>
                </button>
              ))}
            </div>
          </Card>
          {current && <Detail key={current} id={current} onDone={() => { setSel(null); q.refetch(); }} />}
        </div>
      )}
    </>
  );
}

function Detail({ id, onDone }: { id: string; onDone: () => void }) {
  const { pid } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const proj = useProject();
  const owner = proj.data?.permissions?.includes("decide_proposals");
  const q = useQuery<Proposal>({ queryKey: ["proposal", id], queryFn: () => api(`/v1/proposals/${id}`) });
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const p = q.data;
  if (!p) return <Loading />;
  const ops: any[] = p.kind === "patch" ? p.patch.ops || [] : [];
  const decide = async (action: "accept" | "reject", extra: any = {}) => {
    setBusy(true);
    try {
      const edited = Object.keys(edits).length ? ops.map((o, i) => ({ ...o, text: edits[i] ?? o.text })) : undefined;
      await api(`/v1/proposals/${id}/${action}`, { body: { note, edited_ops: action === "accept" ? edited : undefined, ...extra } });
      toast.ok(action === "accept" ? "قُبل المقترح وأُنشئت مراجعة جديدة" : "رُفض المقترح — لم يتغير شيء");
      ["dashboard", "proposals", "facts", "tree"].forEach((k) => qc.invalidateQueries({ queryKey: [k, pid] }));
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.type === "/problems/stale-proposal") {
        if (confirm("تغيّر المستند منذ إنشاء المقترح. هل تطبّقه على النسخة الحالية إن كان المقطع ما يزال مطابقاً حرفياً؟")) {
          setBusy(false);
          return decide("accept", { allow_rebase: true });
        }
      } else toast.error(e);
      q.refetch();
    } finally { setBusy(false); }
  };
  return (
    <Card title={p.title} actions={<><span className="badge">{p.risk_level}</span><Status value={p.certainty} /><span className="badge info">مولَّد آلياً</span></>}>
      <div className="stack">
        <div className="alert info"><strong>المبرر:</strong> {p.rationale || "—"}</div>
        <div className="row dim"><span>الأصل: <span className="mono">{p.agent_id}/{p.skill_id}</span></span>
          {p.target_revision_id && <span>نسخة الأساس: <span className="mono">{p.target_revision_id.slice(0, 8)}</span></span>}
          {p.preview?.stale && <span className="badge warn">المستند تغيّر بعد إنشاء المقترح</span>}</div>
        {p.kind === "patch" && (p.preview?.applicable === false
          ? <div className="alert bad">لا يمكن تطبيقه: {p.preview.error}</div>
          : <DiffView segs={p.preview?.diff || []} />)}
        {p.kind === "fact" && <div className="evidence"><strong>{p.patch.statement}</strong><div className="dim">{p.patch.predicate} = {String(p.patch.object?.value)}</div></div>}
        {p.kind === "note" && <pre className="quote" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(p.patch.alternative || p.patch, null, 1)}</pre>}
        <EvidenceList items={p.evidence_refs} onOpen={(e) => e.node_id && nav(`/p/${pid}/write/${e.node_id}`)} />
        {owner && p.state === "pending" && p.kind === "patch" && ops.some((o) => o.op === "replace_text") && (
          <details>
            <summary className="muted" style={{ cursor: "pointer" }}>تعديل البديل قبل القبول (Modify)</summary>
            <div className="stack" style={{ marginTop: 8 }}>{ops.map((o, i) => o.op === "replace_text" && (
              <Field key={i} label={`«${o.expected}» ←`}><input className="input" value={edits[i] ?? o.text} onChange={(e) => setEdits({ ...edits, [i]: e.target.value })} /></Field>
            ))}</div>
          </details>
        )}
        {owner && (p.state === "pending" || p.state === "stale") && (
          <>
            <textarea className="input" style={{ minHeight: 50 }} value={note} onChange={(e) => setNote(e.target.value)} placeholder="ملاحظة على القرار (اختيارية)" />
            <div className="row">
              {p.state === "pending" && <button className="btn primary" disabled={busy} onClick={() => decide("accept")}>{Object.keys(edits).length ? "قبول مع تعديلي" : "قبول"}</button>}
              {p.kind === "fact" && p.state === "pending" && <button className="btn gold" disabled={busy} onClick={() => decide("accept", { as_canon: true })}>قبول واعتماد في الكانون</button>}
              <button className="btn danger" disabled={busy} onClick={() => decide("reject")}>رفض</button>
            </div>
          </>
        )}
        {!owner && <div className="alert warn">القرار في المقترحات حق لصاحب الرواية؛ يمكنك الاطلاع والتعليق فقط.</div>}
      </div>
    </Card>
  );
}
