import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ConflictItem } from "../api/types";
import { useProject } from "../App";
import { Icon } from "../components/Icon";
import { Card, Empty, EvidenceList, Kpi, Loading, Modal, Severity, Status, Tabs, useToast } from "../components/ui";
import { when } from "../lib/arabic";

export function ContinuityPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const proj = useProject();
  const can = proj.data?.permissions?.includes("bible");
  const [state, setState] = useState<"open" | "waived" | "resolved" | "all">("open");
  const q = useQuery<{ items: ConflictItem[] }>({ queryKey: ["conflicts", pid, state], queryFn: () => api(`/v1/projects/${pid}/conflicts?state=${state}`) });
  const [act, setAct] = useState<{ c: ConflictItem; action: "waive" | "resolve" | "dismiss" } | null>(null);
  const [note, setNote] = useState("");
  const scan = useMutation({
    mutationFn: () => api(`/v1/projects/${pid}/continuity/scan`, { method: "POST" }),
    onSuccess: (s: any) => { toast.ok(`اكتمل الفحص: ${s.found} قائم · ${s.created} جديد · ${s.auto_resolved} زال`); qc.invalidateQueries({ queryKey: ["conflicts", pid] }); qc.invalidateQueries({ queryKey: ["dashboard", pid] }); },
    onError: toast.error,
  });
  const resolve = useMutation({
    mutationFn: () => api(`/v1/projects/${pid}/conflicts/${act!.c.id}/resolve`, { body: { action: act!.action, note } }),
    onSuccess: () => { setAct(null); setNote(""); qc.invalidateQueries({ queryKey: ["conflicts", pid] }); qc.invalidateQueries({ queryKey: ["dashboard", pid] }); },
    onError: toast.error,
  });
  const items = q.data?.items || [];
  const count = (s: string) => items.filter((c) => c.severity === s).length;
  return (
    <>
      <div className="page-head">
        <div className="grow"><div className="eyebrow">CONTINUITY WATCH · A07</div><h1>مراقبة الاستمرارية</h1>
          <div className="muted">كل تنبيه مدعوم بشاهدين على الأقل. الاختلاف المقصود (راوٍ غير موثوق، استرجاع) يُعفى بسبب مكتوب ولا يُعاد فتحه.</div></div>
        {can && <button className="btn gold" onClick={() => scan.mutate()} disabled={scan.isPending}><Icon name="scan" size={16} /> {scan.isPending ? "جارٍ الفحص…" : "فحص الآن"}</button>}
      </div>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="عالية" value={count("high")} tone={count("high") ? "bad" : "ok"} />
        <Kpi label="متوسطة" value={count("medium")} tone="gold" />
        <Kpi label="منخفضة" value={count("low")} />
        <Kpi label="القواعد الفعالة" value="11" sub="العمر ×3 · الوفاة · الحدث ×4 · المكان · الأسماء · الحقائق" />
      </div>
      <Tabs value={state} onChange={setState} items={[["open", "مفتوحة"], ["waived", "مُعفاة"], ["resolved", "محلولة"], ["all", "الكل"]]} />
      {q.isLoading ? <Loading /> : !items.length ? <Card><Empty title="لا تعارضات في هذا العرض" /></Card> : (
        <div className="stack">
          {items.map((c) => (
            <Card key={c.id} title={<span className="row"><Severity level={c.severity} /> {c.title}</span>}
              actions={<><span className="mono dim">{c.rule}</span><Status value={c.state} /></>}>
              <p>{c.explanation}</p>
              <EvidenceList items={c.evidence} onOpen={(e) => e.node_id && nav(`/p/${pid}/write/${e.node_id}`)} />
              {c.resolution_note && <div className="alert info" style={{ marginTop: 8 }}>{c.resolution_note}</div>}
              {can && c.state === "open" && (
                <div className="row" style={{ marginTop: 10 }}>
                  <button className="btn sm" onClick={() => setAct({ c, action: "resolve" })}>عولج في النص</button>
                  <button className="btn sm gold" onClick={() => setAct({ c, action: "waive" })}>إعفاء مسبب (مقصود)</button>
                  <button className="btn sm ghost" onClick={() => setAct({ c, action: "dismiss" })}>إنذار كاذب</button>
                </div>
              )}
              {can && c.state !== "open" && <button className="btn sm ghost" style={{ marginTop: 8 }} onClick={() => api(`/v1/projects/${pid}/conflicts/${c.id}/resolve`, { body: { action: "reopen" } }).then(() => qc.invalidateQueries({ queryKey: ["conflicts", pid] }))}>إعادة فتح</button>}
              <div className="dim" style={{ marginTop: 6 }}>رُصد {when(c.created_at)}</div>
            </Card>
          ))}
        </div>
      )}
      {act && (
        <Modal title={{ waive: "إعفاء مسبب", resolve: "تأكيد المعالجة", dismiss: "استبعاد كإنذار كاذب" }[act.action]} onClose={() => setAct(null)}
          footer={<button className="btn primary" disabled={act.action === "waive" && note.trim().length < 3} onClick={() => resolve.mutate()}>تأكيد</button>}>
          <p className="muted">{act.c.title}</p>
          <textarea className="input" autoFocus value={note} onChange={(e) => setNote(e.target.value)}
            placeholder={act.action === "waive" ? "السبب (إلزامي): مثلاً «راوٍ غير موثوق يكذب في عمره عمداً»" : "ملاحظة اختيارية"} />
          <div className="dim" style={{ marginTop: 6 }}>الإعفاء لا يغيّر أي حقيقة في الكانون، ويبقى سارياً عبر الفحوص اللاحقة.</div>
        </Modal>
      )}
    </>
  );
}
