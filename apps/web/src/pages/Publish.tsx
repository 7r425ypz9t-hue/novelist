import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, download } from "../api/client";
import { useProject } from "../App";
import { Icon } from "../components/Icon";
import { Card, Empty, Status, useToast } from "../components/ui";
import { fmt, when } from "../lib/arabic";

const FORMATS: { id: "docx" | "pdf" | "epub" | "md"; title: string; desc: string }[] = [
  { id: "docx", title: "Word ‏DOCX", desc: "فقرات ثنائية الاتجاه، خط Noto Naskh Arabic، فهرس تلقائي، فاصل صفحات لكل فصل، حواشٍ." },
  { id: "pdf", title: "PDF ‏A5", desc: "تشكيل الحروف وإعادة الترتيب، ضبط الأسطر، فهرس بأرقام الصفحات، علامات تنقل، أرقام عربية." },
  { id: "epub", title: "EPUB 3", desc: "تقدّم صفحات من اليمين، لغة ar، فهرس nav وtoc.ncx، خط مضمّن، حواشٍ قابلة للنقر." },
  { id: "md", title: "Markdown", desc: "نص مجمّع خفيف لأدوات أخرى ولمراجعة الفروق." },
];

export function PublishPage() {
  const { pid } = useParams();
  const toast = useToast();
  const proj = useProject();
  const can = proj.data?.permissions?.includes("export");
  const list = useQuery<any>({ queryKey: ["exports", pid], queryFn: () => api(`/v1/projects/${pid}/exports`) });
  const make = useMutation({
    mutationFn: (format: string) => api(`/v1/projects/${pid}/exports`, { body: { format } }),
    onSuccess: async (e: any) => { toast.ok(`جاهز: ${e.filename}`); list.refetch(); await download(`/v1/exports/${e.id}/download`); },
    onError: toast.error,
  });
  const checklist = useQuery<any>({ queryKey: ["dashboard", pid], queryFn: () => api(`/v1/projects/${pid}/dashboard`) });
  const d = checklist.data;
  return (
    <>
      <div className="page-head"><div className="grow"><div className="eyebrow">النشر والإخراج · A12</div><h1>التصدير والنشر</h1>
        <div className="muted">لا يُرسل أي ملف إلى طرف خارجي؛ التصدير يُنزَّل إلى جهازك فقط، مع بصمة SHA-256 للتحقق.</div></div></div>
      {d && (
        <div className="grid g4" style={{ marginBottom: 16 }}>
          <Check ok={d.open_conflicts.high === 0} label="لا تعارضات عالية مفتوحة" />
          <Check ok={d.pending_proposals === 0} label="لا مقترحات معلقة" />
          <Check ok={d.counts.empty_units === 0} label="لا وحدات فارغة" />
          <Check ok={d.counts.unverified_citations === 0} label="لا ادعاءات «غير متحقق»" />
        </div>
      )}
      <div className="grid g4">
        {FORMATS.map((f) => (
          <div key={f.id} className="card"><div className="card-b stack">
            <h2>{f.title}</h2><div className="muted" style={{ minHeight: 66 }}>{f.desc}</div>
            <button className="btn primary" disabled={!can || make.isPending} onClick={() => make.mutate(f.id)}><Icon name="publish" size={16} /> إنشاء وتنزيل</button>
          </div></div>
        ))}
      </div>
      <Card title="سجل التصدير" icon="history" className="" bodyClass="card-b">
        {!list.data?.items.length ? <Empty title="لا تصديرات بعد" /> : (
          <table className="table"><thead><tr><th>الملف</th><th>الصيغة</th><th>الحجم</th><th>SHA-256</th><th>الحالة</th><th>متى</th><th /></tr></thead>
            <tbody>{list.data.items.map((e: any) => (
              <tr key={e.id}><td>{e.filename}</td><td className="mono">{e.format}</td><td className="mono">{fmt(e.size)}</td>
                <td className="mono dim">{e.sha256.slice(0, 16)}…</td><td><Status value={e.status} /></td><td className="dim">{when(e.created_at)}</td>
                <td>{e.status === "done" && <button className="btn sm" onClick={() => download(`/v1/exports/${e.id}/download`)}>تنزيل</button>}</td></tr>))}
            </tbody></table>
        )}
      </Card>
    </>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return <div className={`card kpi ${ok ? "ok" : "gold"}`}><div className="row"><span className={`dot ${ok ? "ok" : "warn"}`} /> {label}</div></div>;
}
