import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useMe } from "../App";
import { Card, Empty, Kpi, useToast } from "../components/ui";
import { fmt, when } from "../lib/arabic";

export function AdminPage() {
  const me = useMe();
  const toast = useToast();
  const health = useQuery<any>({ queryKey: ["admin-health"], queryFn: () => api("/v1/admin/health"), refetchInterval: 10000, enabled: !!me.data?.is_admin });
  const metrics = useQuery<any>({ queryKey: ["admin-metrics"], queryFn: () => api("/v1/admin/metrics"), refetchInterval: 15000, enabled: !!me.data?.is_admin });
  const users = useQuery<any>({ queryKey: ["admin-users"], queryFn: () => api("/v1/admin/users"), enabled: !!me.data?.is_admin });
  const projects = useQuery<any>({ queryKey: ["admin-projects"], queryFn: () => api("/v1/admin/projects"), enabled: !!me.data?.is_admin });
  const [filter, setFilter] = useState("");
  const audit = useQuery<any>({ queryKey: ["admin-audit", filter], queryFn: () => api(`/v1/admin/audit?limit=150${filter ? `&action=${encodeURIComponent(filter)}` : ""}`), enabled: !!me.data?.is_admin });
  if (!me.data?.is_admin) return <Card><Empty title="هذه اللوحة لمسؤول النظام" /></Card>;
  const h = health.data, m = metrics.data;
  const toggle = async (u: any) => {
    try { await api(`/v1/admin/users/${u.id}/active?active=${!u.is_active}`, { method: "POST" }); users.refetch(); } catch (e) { toast.error(e); }
  };
  return (
    <>
      <div className="page-head"><div className="grow"><div className="eyebrow">تشغيل النظام</div><h1>لوحة مسؤول النظام</h1>
        <div className="muted">تشغيل ومراقبة تقنية فقط: لا يرى المسؤول نصوص المخطوطات، وعناوين المشاريع الخاصة محجوبة، والسجلات منقّحة.</div></div></div>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="الخدمة" value={h ? <span className="row" style={{ justifyContent: "flex-end" }}><span className="dot ok" /> {h.status.toUpperCase()}</span> : "…"} sub={h && `v${h.version} · uptime ${Math.round(h.uptime_s / 60)} د`} tone="ok" />
        <Kpi label="قاعدة البيانات" value={h ? `${h.database.latency_ms} ms` : "…"} sub={h?.database.engine} />
        <Kpi label="التخزين" value={h ? (h.storage.ok ? "OK" : "ERR") : "…"} sub={h ? (h.encryption_at_rest ? "تشفير المحتوى: مفعّل (AES-256-GCM)" : "تشفير المحتوى: غير مفعّل") : undefined} tone={h?.storage.ok ? (h.encryption_at_rest ? "ok" : "gold") : "bad"} />
        <Kpi label="مزود النماذج" value={h ? (h.provider.available ? h.provider.name : "معطّل") : "…"} sub={h?.provider.destination} tone="gold" />
      </div>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <Kpi label="المستخدمون / المشاريع" value={m ? `${m.users} / ${m.projects}` : "…"} />
        <Kpi label="الكلمات المخزنة" value={m ? fmt(m.words) : "…"} sub={m && `${fmt(m.revisions)} مراجعة ثابتة`} />
        <Kpi label="المصادر / المقاطع" value={m ? `${m.sources} / ${m.chunks}` : "…"} sub={m && `${m.flagged_chunks} مقطع مشبوه معزول`} tone={m?.flagged_chunks ? "gold" : ""} />
        <Kpi label="تشغيلات الوكلاء" value={m ? Object.values(m.runs as Record<string, number>).reduce((a, b) => a + b, 0) : "…"} sub={m && `${fmt(m.tokens_used)} رمز · ${m.pending_proposals} مقترح معلق`} />
      </div>
      <div className="grid g2">
        <Card title="المستخدمون">
          <table className="table"><thead><tr><th>المستخدم</th><th>مشاريع</th><th>الحالة</th><th /></tr></thead><tbody>
            {users.data?.items.map((u: any) => (
              <tr key={u.id}><td>{u.display_name} {u.is_admin && <span className="badge gold">مسؤول</span>}<div className="dim mono">{u.email}</div></td>
                <td className="mono">{u.projects}</td><td>{u.is_active ? <span className="badge ok">نشط</span> : <span className="badge bad">موقوف</span>}</td>
                <td>{u.id !== me.data?.id && <button className="btn sm ghost" onClick={() => toggle(u)}>{u.is_active ? "إيقاف" : "تفعيل"}</button>}</td></tr>))}
          </tbody></table>
        </Card>
        <Card title="المشاريع (محجوبة الخصوصية)">
          <table className="table"><tbody>{projects.data?.items.map((p: any) => (
            <tr key={p.id}><td>{p.title}</td><td className="mono dim">{p.id.slice(0, 8)}</td><td className="dim">{when(p.created_at)}</td></tr>))}
          </tbody></table>
        </Card>
        <Card title="حدود التشغيل">
          {h && <table className="table"><tbody>{Object.entries(h.limits).map(([k, v]: any) => <tr key={k}><td className="mono">{k}</td><td className="mono">{v}</td></tr>)}
            <tr><td className="mono">active_runs</td><td className="mono">{h.worker.active_runs}</td></tr></tbody></table>}
        </Card>
        <Card title="سجل التدقيق (منقّح)" actions={<input className="input" style={{ width: 180, height: 28 }} placeholder="تصفية: project. / auth." value={filter} onChange={(e) => setFilter(e.target.value)} />}>
          <div className="scroll-y">
            <table className="table"><tbody>{audit.data?.items.map((e: any) => (
              <tr key={e.id}><td className="dim" style={{ whiteSpace: "nowrap" }}>{when(e.at)}</td><td className="mono">{e.action}</td>
                <td className="mono dim">{e.actor_type}</td><td className="mono dim" style={{ fontSize: 11 }}>{Object.entries(e.metadata).map(([k, v]) => `${k}=${v}`).join(" ")}</td></tr>))}
            </tbody></table>
          </div>
        </Card>
      </div>
    </>
  );
}
