import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { AreaChart, BarChart, Donut } from "../components/charts";
import { Icon } from "../components/Icon";
import { Card, Empty, Kpi, Loading, Status } from "../components/ui";
import { ago, fmt } from "../lib/arabic";

export function DashboardPage() {
  const { pid } = useParams();
  const q = useQuery<any>({ queryKey: ["dashboard", pid], queryFn: () => api(`/v1/projects/${pid}/dashboard`), refetchInterval: 15000 });
  const conflicts = useQuery<any>({ queryKey: ["conflicts", pid, "open"], queryFn: () => api(`/v1/projects/${pid}/conflicts?state=open`) });
  const proposals = useQuery<any>({ queryKey: ["proposals", pid, "pending"], queryFn: () => api(`/v1/projects/${pid}/proposals?state=pending&limit=6`) });
  if (q.isLoading || !q.data) return <Loading />;
  const d = q.data;
  const oc = d.open_conflicts;
  const scenes = d.scene_status as Record<string, number>;
  return (
    <>
      <div className="page-head">
        <div className="grow">
          <div className="eyebrow">MISSION CONTROL</div>
          <h1>مركز القيادة</h1>
          <div className="muted">{d.project.logline || "حدّد الجملة المحورية من الإعدادات لتقيس الفصول عليها."}</div>
        </div>
        <Link className="btn primary" to={`/p/${pid}/write`}><Icon name="write" size={16} /> متابعة الكتابة</Link>
        <Link className="btn gold" to={`/p/${pid}/agents`}><Icon name="agents" size={16} /> تشغيل فحص شامل</Link>
      </div>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="الكلمات" value={fmt(d.words)} sub={d.word_goal ? `من هدف ${fmt(d.word_goal)}` : "بلا هدف محدد"} progress={d.progress} tone="gold" />
        <Kpi label="البنية" value={`${d.counts.chapters} / ${d.counts.scenes}`} sub={`فصول / مشاهد · ${d.counts.empty_units} وحدة فارغة`} />
        <Kpi label="تعارضات مفتوحة" value={oc.high + oc.medium + oc.low} sub={`${oc.high} عالية · ${oc.medium} متوسطة · ${oc.low} منخفضة`} tone={oc.high ? "bad" : "ok"} />
        <Kpi label="مقترحات بانتظار قرارك" value={d.pending_proposals} sub="لا يتغير النص إلا بموافقتك" tone={d.pending_proposals ? "gold" : "ok"} />
      </div>

      <div className="grid g3">
        <Card title="الكلمات لكل فصل" icon="dashboard" className="span2">
          <BarChart data={d.per_chapter.map((c: any) => ({ label: c.label.split(" — ")[0], value: c.words }))} />
        </Card>
        <Card title="حالة المشاهد" icon="write">
          {Object.keys(scenes).length ? (
            <Donut parts={[
              { label: "فكرة", value: scenes.idea || 0, color: "var(--text-3)" },
              { label: "مسودة", value: scenes.draft || 0, color: "var(--accent)" },
              { label: "منقّح", value: scenes.revised || 0, color: "var(--gold)" },
              { label: "نهائي", value: scenes.final || 0, color: "var(--ok)" },
            ]} />
          ) : <Empty title="لا مشاهد بعد" />}
        </Card>

        <Card title="نشاط الكتابة — آخر 30 يوماً" icon="insight" className="span2">
          <AreaChart data={d.daily_words.map((x: any) => ({ label: x.date.slice(5), value: x.words }))} />
        </Card>
        <Card title="المصادر والتحقق" icon="sources">
          <div className="stack">
            <div className="row between"><span className="muted">ملفات المصادر</span><strong className="num">{d.counts.sources}</strong></div>
            <div className="row between"><span className="muted">استشهادات «غير متحقق»</span><strong className="num">{d.counts.unverified_citations}</strong></div>
            <Link className="btn sm" to={`/p/${pid}/sources`}>فتح المكتبة</Link>
          </div>
        </Card>

        <Card title="أبرز تنبيهات الاستمرارية" icon="continuity" className="span2"
          actions={<Link className="btn sm" to={`/p/${pid}/continuity`}>كل التعارضات</Link>}>
          {conflicts.data?.items?.length ? (
            <table className="table"><tbody>
              {conflicts.data.items.slice(0, 5).map((c: any) => (
                <tr key={c.id}><td style={{ width: 90 }}><span className={`badge ${c.severity === "high" ? "bad" : c.severity === "medium" ? "warn" : "info"}`}>{c.severity === "high" ? "عالٍ" : c.severity === "medium" ? "متوسط" : "منخفض"}</span></td>
                  <td><strong>{c.title}</strong><div className="dim">{c.explanation}</div></td></tr>
              ))}
            </tbody></table>
          ) : <Empty title="لا تعارضات مفتوحة">شغّل فحص الاستمرارية بعد تحديث الشخصيات والأحداث.</Empty>}
        </Card>
        <Card title="آخر تشغيلات الوكلاء" icon="agents">
          {d.recent_runs.length ? (
            <div className="stack" style={{ gap: 6 }}>
              {d.recent_runs.map((r: any) => (
                <div key={r.id} className="row between"><span className="mono">{r.agent_id}</span><Status value={r.status} /><span className="dim">{ago(r.created_at)}</span></div>
              ))}
            </div>
          ) : <Empty title="لم يُشغَّل أي وكيل" />}
        </Card>

        <Card title="مقترحات معلقة" icon="proposals" className="span3"
          actions={<Link className="btn sm" to={`/p/${pid}/proposals`}>غرفة النقد</Link>}>
          {proposals.data?.items?.length ? (
            <table className="table"><thead><tr><th>الوكيل</th><th>المقترح</th><th>اليقين</th><th>المخاطرة</th></tr></thead><tbody>
              {proposals.data.items.map((p: any) => (
                <tr key={p.id}><td className="mono">{p.agent_id}/{p.skill_id}</td><td>{p.title}</td><td><Status value={p.certainty} /></td><td><span className="badge">{p.risk_level}</span></td></tr>
              ))}
            </tbody></table>
          ) : <Empty title="لا مقترحات معلقة" />}
        </Card>
      </div>
    </>
  );
}
