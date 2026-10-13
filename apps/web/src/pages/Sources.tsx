import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Hit, Source } from "../api/types";
import { useProject } from "../App";
import { Icon } from "../components/Icon";
import { Card, Empty, Field, Modal, Status, useToast } from "../components/ui";
import { fmt, when } from "../lib/arabic";

const LICENSES: [string, string][] = [
  ["owned", "ملكي (من تأليفي)"], ["licensed", "مرخّص"], ["public_domain", "ملك عام"], ["permission", "بإذن صاحب الحق"], ["unknown", "غير معروف — لن يُستخدم"],
];

export function SourcesPage() {
  const { pid } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const proj = useProject();
  const can = proj.data?.permissions?.includes("sources");
  const q = useQuery<{ items: Source[] }>({ queryKey: ["sources", pid], queryFn: () => api(`/v1/projects/${pid}/sources`) });
  const cits = useQuery<any>({ queryKey: ["citations", pid], queryFn: () => api(`/v1/projects/${pid}/citations`) });
  const [upload, setUpload] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<any>(null);
  const [view, setView] = useState<Source | null>(null);
  const ask = useMutation({
    mutationFn: () => api(`/v1/projects/${pid}/research/query`, { body: { question } }),
    onSuccess: setAnswer, onError: toast.error,
  });
  const cite = async (h: Hit | null) => {
    try {
      await api(`/v1/projects/${pid}/citations`, { body: { claim_text: question, source_chunk_id: h?.chunk_id } });
      toast.ok(h ? "رُبط الادعاء بالمصدر" : "سُجّل الادعاء «غير متحقق»");
      cits.refetch();
      qc.invalidateQueries({ queryKey: ["dashboard", pid] });
    } catch (e) { toast.error(e); }
  };
  const patch = async (s: Source, body: any) => {
    try { await api(`/v1/projects/${pid}/sources/${s.id}`, { method: "PATCH", body }); q.refetch(); } catch (e) { toast.error(e); }
  };
  const del = async (s: Source) => {
    if (!confirm(`حذف «${s.title}» ومقاطعه من الاسترجاع نهائياً؟ الاستشهادات المرتبطة تعود «غير متحقق».`)) return;
    try { await api(`/v1/projects/${pid}/sources/${s.id}`, { method: "DELETE" }); q.refetch(); cits.refetch(); } catch (e) { toast.error(e); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); if (question.trim().length > 1) ask.mutate(); };
  return (
    <>
      <div className="page-head">
        <div className="grow"><div className="eyebrow">البحث والتوثيق · A05</div><h1>المصادر والشواهد</h1>
          <div className="muted">بحث محلي مقيّد بمصادر هذا المشروع المرخّصة: يطابق الصيغ الصرفية والمرادفات الشائعة والأسماء البديلة من الكتاب المرجعي، ويبيّن كل توسعة. النص المسترجَع بيانات لا تعليمات؛ وعند ضعف الدليل: «غير متحقق».</div></div>
        {can && <button className="btn primary" onClick={() => setUpload(true)}><Icon name="upload" size={16} /> رفع مصدر</button>}
      </div>

      <div className="grid g3">
        <Card title="اسأل مصادرك" className="span2" icon="search">
          <form className="row" onSubmit={submit}>
            <input className="input" style={{ flex: 1 }} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="مثلاً: متى افتُتح الميناء الجديد؟" />
            <button className="btn primary" disabled={ask.isPending}>بحث</button>
          </form>
          {answer && (
            <div className="stack" style={{ marginTop: 12 }}>
              <div className={`alert ${answer.verdict === "evidence_found" ? "ok" : "warn"}`}>{answer.message}</div>
              {answer.hits.map((h: Hit) => (
                <div key={h.chunk_id} className="evidence">
                  <div className="row between">
                    <span><strong>{h.source_title}</strong> · <span className="mono">{h.locator}</span></span>
                    <span className="row"><span className="badge">تغطية {Math.round(h.term_coverage * 100)}%</span>
                      {h.suspicious_instructions.length > 0 && <span className="badge bad" title={h.suspicious_instructions.join(" | ")}>يحوي عبارات تشبه أوامر — بيانات فقط</span>}</span>
                  </div>
                  {!!h.matched_via?.length && (
                    <div className="pill-list" style={{ marginTop: 6 }}>
                      {h.matched_via.map((m, i) => (
                        <span key={i} className="badge info">{({ morph: "تطابق صرفي", alias: "اسم بديل", synonym: "مرادف" } as const)[m.kind]}: {m.term} ← {m.matched}</span>
                      ))}
                    </div>
                  )}
                  <div className="quote" style={{ marginTop: 6 }}>{h.content}</div>
                  <button className="btn sm" style={{ marginTop: 6 }} onClick={() => cite(h)}>اربط الادعاء بهذا المقطع</button>
                </div>
              ))}
              {answer.verdict !== "evidence_found" && <button className="btn sm gold" onClick={() => cite(null)}>سجّل الادعاء «غير متحقق»</button>}
            </div>
          )}
        </Card>
        <Card title="الاستشهادات" icon="link">
          <div className="stack scroll-y" style={{ gap: 6 }}>
            {!cits.data?.items.length && <Empty title="لا استشهادات" />}
            {cits.data?.items.map((c: any) => (
              <div key={c.id} className="evidence">
                <div className="row between"><Status value={c.verification_state === "verified" ? "supported" : "speculative"} /><span className="mono dim">{c.locator || "—"}</span></div>
                <div style={{ fontSize: 13 }}>{c.claim_text}</div>
                {c.verification_state !== "verified" && <div className="dim">غير متحقق {c.note && `· ${c.note}`}</div>}
              </div>
            ))}
          </div>
        </Card>

        <Card title={`المكتبة (${q.data?.items.length ?? 0})`} className="span3" icon="sources">
          {!q.data?.items.length ? <Empty title="لا مصادر بعد">ارفع PDF أو DOCX أو TXT أو MD مع تحديد حالة الحقوق.</Empty> : (
            <table className="table"><thead><tr><th>المصدر</th><th>النوع</th><th>الحقوق</th><th>موافقة الاستخدام</th><th>الفهرسة</th><th>تنبيهات</th><th /></tr></thead>
              <tbody>{q.data.items.map((s) => (
                <tr key={s.id}>
                  <td><button className="btn ghost sm" onClick={() => setView(s)}><Icon name="file" size={14} /> {s.title || s.filename}</button><div className="dim">{fmt(s.size)} بايت · {when(s.created_at)}</div></td>
                  <td className="mono">{s.file_type.toUpperCase()}{s.page_count ? ` · ${s.page_count}ص` : ""}</td>
                  <td>{can ? <select className="select" value={s.license_state} onChange={(e) => patch(s, { license_state: e.target.value })}>{LICENSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select> : s.license_state}</td>
                  <td><label className="check"><input type="checkbox" checked={s.usage_consent} disabled={!can} onChange={(e) => patch(s, { usage_consent: e.target.checked })} /> {s.usable ? <span className="badge ok">يُستخدم</span> : <span className="badge">مستبعد</span>}</label></td>
                  <td><Status value={s.ingestion_status} /></td>
                  <td>{s.flagged_chunks ? <span className="badge bad">{s.flagged_chunks} مقطع مشبوه</span> : <span className="dim">—</span>}</td>
                  <td>{can && <button className="btn sm danger" onClick={() => del(s)}><Icon name="trash" size={14} /></button>}</td>
                </tr>))}
              </tbody></table>
          )}
        </Card>
      </div>
      {upload && <UploadModal onClose={() => setUpload(false)} onDone={() => { setUpload(false); q.refetch(); }} />}
      {view && <ChunksModal source={view} onClose={() => setView(null)} />}
    </>
  );
}

function UploadModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { pid } = useParams();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [license, setLicense] = useState("owned");
  const [consent, setConsent] = useState(false);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const m = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("file", file!);
      fd.append("license_state", license);
      fd.append("usage_consent", String(consent));
      fd.append("title", title);
      fd.append("author", author);
      return api<Source>(`/v1/projects/${pid}/sources`, { form: fd });
    },
    onSuccess: (s) => { toast.ok(s.flagged_chunks ? `فُهرس المصدر — ${s.flagged_chunks} مقطع يحوي عبارات تشبه أوامر وسُيعامل بيانات فقط` : "فُهرس المصدر"); onDone(); },
    onError: toast.error,
  });
  return (
    <Modal title="رفع مصدر" onClose={onClose} footer={<button className="btn primary" disabled={!file || m.isPending} onClick={() => m.mutate()}>رفع وفهرسة</button>}>
      <div className="form-grid">
        <Field label="الملف (PDF · DOCX · TXT · MD)" full><input className="input" type="file" accept=".pdf,.docx,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
        <Field label="العنوان"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="المؤلف"><input className="input" value={author} onChange={(e) => setAuthor(e.target.value)} /></Field>
        <Field label="حالة الحقوق" full><select className="select" value={license} onChange={(e) => setLicense(e.target.value)}>{LICENSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <label className="check full"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> أوافق على استخدام هذا الملف في البحث والاستشهاد داخل هذا المشروع فقط.</label>
      </div>
    </Modal>
  );
}

function ChunksModal({ source, onClose }: { source: Source; onClose: () => void }) {
  const { pid } = useParams();
  const q = useQuery<any>({ queryKey: ["chunks", source.id], queryFn: () => api(`/v1/projects/${pid}/sources/${source.id}/chunks`) });
  return (
    <Modal title={`مقاطع: ${source.title}`} wide onClose={onClose}>
      <div className="stack">{q.data?.items.map((c: any) => (
        <div key={c.id} className="evidence">
          <div className="row between"><span className="mono">{c.locator}</span>{c.flags?.suspicious_instructions && <span className="badge bad">عبارات تشبه أوامر — لا تُنفَّذ</span>}</div>
          <div className="quote" style={{ marginTop: 6 }}>{c.content}</div>
        </div>
      ))}</div>
    </Modal>
  );
}
