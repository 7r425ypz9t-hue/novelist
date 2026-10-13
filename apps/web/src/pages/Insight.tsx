import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { useProject } from "../App";
import { Card, Empty, Field, Modal, useToast } from "../components/ui";

export function InsightPage() {
  const { pid } = useParams();
  const toast = useToast();
  const proj = useProject();
  const owner = proj.data?.permissions?.includes("manage");
  const styles = useQuery<any>({ queryKey: ["styles", pid], queryFn: () => api(`/v1/projects/${pid}/style-profiles`) });
  const nlqi = useQuery<any>({ queryKey: ["nlqi", pid], queryFn: () => api(`/v1/projects/${pid}/nlqi`) });
  const [newStyle, setNewStyle] = useState(false);
  const [rate, setRate] = useState(false);
  const erase = async (id: string) => {
    if (!confirm("محو البصمة نهائياً؟ تُحذف الخصائص وتُلغى الموافقة المرتبطة.")) return;
    try { await api(`/v1/projects/${pid}/style-profiles/${id}`, { method: "DELETE" }); styles.refetch(); toast.ok("مُحيت البصمة"); } catch (e) { toast.error(e); }
  };
  const n = nlqi.data;
  return (
    <>
      <div className="page-head"><div className="grow"><div className="eyebrow">STYLE & QUALITY</div><h1>البصمة الأسلوبية والتقييم</h1>
        <div className="muted">البصمة تحمي صوتك أنت وتُبنى من عيّنات تملكها فقط. مؤشر NLQI تجميع لتقديرات بشرية بأوزانك — ليس حكماً آلياً.</div></div></div>
      <div className="grid g2">
        <Card title="البصمة الأسلوبية (LSIS)" icon="spark" actions={owner && <button className="btn sm primary" onClick={() => setNewStyle(true)}>بصمة جديدة</button>}>
          {!styles.data?.items.length ? <Empty title="لا بصمة بعد">تُستخدم لاحقاً لتنبيهك حين ينحرف فصل عن صوتك المعتاد (SK08).</Empty> : styles.data.items.map((s: any) => (
            <div key={s.id} className="stack">
              <div className="row between"><strong>{s.name}</strong><span className="dim">{s.sample_count} عينة · {s.features.words} كلمة</span></div>
              <table className="table"><tbody>{Object.entries(s.labels).map(([k, label]: any) => (
                s.features[k] !== undefined && <tr key={k}><td>{label}</td><td className="mono">{s.features[k]}</td></tr>
              ))}</tbody></table>
              {owner && <button className="btn sm danger" onClick={() => erase(s.id)}>محو البصمة</button>}
            </div>
          ))}
        </Card>
        <Card title="مؤشر NLQI التجريبي" icon="insight" actions={<button className="btn sm" onClick={() => setRate(true)}>إضافة تقييم بشري</button>}>
          {!n ? null : (
            <div className="stack">
              <div className="alert warn">{n.disclaimer}</div>
              <div className="row between"><span className="muted">المؤشر المجمّع</span><strong className="mono" style={{ fontSize: 26 }}>{n.index ?? "—"}</strong></div>
              <table className="table"><thead><tr><th>البعد</th><th>الوزن</th><th>المتوسط</th><th>التباين</th><th>مقيّمون</th></tr></thead>
                <tbody>{n.dimensions.map((d: any) => (
                  <tr key={d.key}><td>{d.label}</td><td className="mono">{d.weight}</td><td className="mono">{d.mean ?? "—"}</td>
                    <td>{d.spread !== null ? <span className={`badge ${d.spread >= 2 ? "warn" : ""}`}>{d.spread}</span> : "—"}</td><td className="mono">{d.raters}</td></tr>))}
                </tbody></table>
              {n.assessments.map((a: any) => (
                <div key={a.id} className="evidence"><div className="row between"><strong>{a.rater}</strong><span className="mono">{a.index}</span></div>
                  {Object.entries(a.notes || {}).map(([k, v]: any) => <div key={k} className="dim">{k}: {v}</div>)}</div>
              ))}
            </div>
          )}
        </Card>
      </div>
      {newStyle && <StyleModal onClose={() => setNewStyle(false)} onDone={() => { setNewStyle(false); styles.refetch(); }} />}
      {rate && n && <RateModal dims={n.dimensions} onClose={() => setRate(false)} onDone={() => { setRate(false); nlqi.refetch(); }} />}
    </>
  );
}

function StyleModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { pid } = useParams();
  const toast = useToast();
  const [name, setName] = useState("صوتي");
  const [samples, setSamples] = useState("");
  const [rights, setRights] = useState("own_work");
  const [decl, setDecl] = useState(false);
  const m = useMutation({
    mutationFn: () => api(`/v1/projects/${pid}/style-profiles`, { body: { name, rights_basis: rights, declaration: decl, samples: samples.split(/\n-{3,}\n/).filter((s) => s.trim()) } }),
    onSuccess: () => { toast.ok("أُنشئت البصمة — لم يُخزَّن نص العينات"); onDone(); }, onError: toast.error,
  });
  return (
    <Modal title="بصمة أسلوبية من عينات مملوكة" wide onClose={onClose} footer={<button className="btn primary" disabled={!decl || m.isPending} onClick={() => m.mutate()}>إنشاء</button>}>
      <div className="stack">
        <Field label="الاسم"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="العينات (افصل بين العينات بسطر ---) — 300 كلمة على الأقل"><textarea className="input" style={{ minHeight: 180, fontFamily: "var(--font-text)" }} value={samples} onChange={(e) => setSamples(e.target.value)} /></Field>
        <Field label="أساس الحق"><select className="select" value={rights} onChange={(e) => setRights(e.target.value)}>
          <option value="own_work">نصوص من تأليفي</option><option value="licensed_with_permission">مرخّصة بإذن صريح</option>
          <option value="third_party">نصوص لمؤلف آخر</option><option value="unknown">غير متأكد</option></select></Field>
        <label className="check"><input type="checkbox" checked={decl} onChange={(e) => setDecl(e.target.checked)} /> أقرّ بأنني أملك حق استخدام هذه العينات، وأن البصمة لن تُستخدم لتقليد مؤلف آخر.</label>
        <div className="dim">تُرفض العينات المنسوبة لطرف ثالث أو المجهولة الحقوق. تُحفظ الخصائص الإحصائية وبصمات SHA-256 فقط.</div>
      </div>
    </Modal>
  );
}

function RateModal({ dims, onClose, onDone }: { dims: any[]; onClose: () => void; onDone: () => void }) {
  const { pid } = useParams();
  const toast = useToast();
  const [scores, setScores] = useState<Record<string, number>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [rater, setRater] = useState("");
  const m = useMutation({
    mutationFn: () => api(`/v1/projects/${pid}/nlqi/assessments`, { body: { scores, notes, rater_label: rater } }),
    onSuccess: onDone, onError: toast.error,
  });
  return (
    <Modal title="تقييم بشري بمعايير معلنة" wide onClose={onClose} footer={<button className="btn primary" disabled={!Object.keys(scores).length} onClick={() => m.mutate()}>حفظ</button>}>
      <Field label="اسم المقيّم (اختياري)"><input className="input" value={rater} onChange={(e) => setRater(e.target.value)} /></Field>
      <table className="table" style={{ marginTop: 10 }}><thead><tr><th>البعد</th><th>الدرجة (0–10)</th><th>التعليل المستند إلى مقتطف</th></tr></thead>
        <tbody>{dims.map((d) => (
          <tr key={d.key}><td>{d.label} <span className="dim">({d.weight})</span></td>
            <td style={{ width: 110 }}><input className="input" type="number" min={0} max={10} step={0.5} dir="ltr" value={scores[d.key] ?? ""}
              onChange={(e) => { const v = e.target.value; const next = { ...scores }; if (v === "") delete next[d.key]; else next[d.key] = Number(v); setScores(next); }} /></td>
            <td><input className="input" value={notes[d.key] || ""} onChange={(e) => setNotes({ ...notes, [d.key]: e.target.value })} /></td></tr>))}
        </tbody></table>
    </Modal>
  );
}
