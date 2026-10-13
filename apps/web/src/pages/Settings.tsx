import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, download } from "../api/client";
import { roleLabel, useProject } from "../App";
import type { CalendarDef } from "../components/HijriPicker";
import { Card, Empty, Field, Status, useToast } from "../components/ui";
import { when } from "../lib/arabic";

export function SettingsPage() {
  const { pid } = useParams();
  const proj = useProject();
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const owner = proj.data?.permissions?.includes("manage");
  const [f, setF] = useState<any>(null);
  useEffect(() => { if (proj.data) setF({ ...proj.data, ms: proj.data.manuscripts?.[0] }); }, [proj.data]);
  const members = useQuery<any>({ queryKey: ["members", pid], queryFn: () => api(`/v1/projects/${pid}/members`) });
  const consents = useQuery<any>({ queryKey: ["consents", pid], queryFn: () => api(`/v1/projects/${pid}/consents`) });
  const trash = useQuery<any>({ queryKey: ["trash", pid], queryFn: () => api(`/v1/projects/${pid}/trash`) });
  const cat = useQuery<any>({ queryKey: ["catalog"], queryFn: () => api("/v1/agents/catalog") });
  const [invite, setInvite] = useState({ email: "", role: "commenter" });
  const [confirmTitle, setConfirmTitle] = useState("");
  const save = useMutation({
    mutationFn: async () => {
      await api(`/v1/projects/${pid}`, { method: "PATCH", body: { title: f.title, genre: f.genre, logline: f.logline, description: f.description,
        word_goal: Number(f.word_goal), privacy_mode: f.privacy_mode, ai_enabled: f.ai_enabled } });
      if (f.ms) await api(`/v1/manuscripts/${f.ms.id}`, { method: "PATCH", body: { title: f.ms.title, subtitle: f.ms.subtitle, author_name: f.ms.author_name } });
    },
    onSuccess: () => { toast.ok("حُفظت الإعدادات"); qc.invalidateQueries({ queryKey: ["project", pid] }); },
    onError: toast.error,
  });
  const run = async (p: Promise<unknown>, msg: string) => { try { await p; toast.ok(msg); members.refetch(); consents.refetch(); trash.refetch(); qc.invalidateQueries({ queryKey: ["tree", pid] }); } catch (e) { toast.error(e); } };
  if (!f) return null;
  const provider = cat.data?.provider;
  const activeConsent = consents.data?.items.find((c: any) => c.kind === "external_ai" && !c.revoked_at);
  return (
    <>
      <div className="page-head"><div className="grow"><div className="eyebrow">الضبط والحماية</div><h1>الإعدادات والخصوصية</h1></div>
        {owner && <button className="btn primary" onClick={() => save.mutate()} disabled={save.isPending}>حفظ</button>}</div>
      <div className="grid g2">
        <Card title="المشروع والمخطوط">
          <div className="form-grid">
            <Field label="العنوان"><input className="input" disabled={!owner} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
            <Field label="النوع"><input className="input" disabled={!owner} value={f.genre} onChange={(e) => setF({ ...f, genre: e.target.value })} /></Field>
            <Field label="الجملة المحورية" full><input className="input" disabled={!owner} value={f.logline} onChange={(e) => setF({ ...f, logline: e.target.value })} /></Field>
            <Field label="الوصف" full><textarea className="input" disabled={!owner} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
            <Field label="هدف الكلمات"><input className="input" type="number" disabled={!owner} value={f.word_goal} onChange={(e) => setF({ ...f, word_goal: e.target.value })} /></Field>
            <Field label="اسم المؤلف (للتصدير)"><input className="input" disabled={!owner} value={f.ms?.author_name || ""} onChange={(e) => setF({ ...f, ms: { ...f.ms, author_name: e.target.value } })} /></Field>
            <Field label="العنوان الفرعي" full><input className="input" disabled={!owner} value={f.ms?.subtitle || ""} onChange={(e) => setF({ ...f, ms: { ...f.ms, subtitle: e.target.value } })} /></Field>
          </div>
        </Card>

        <Card title="الخصوصية والذكاء الاصطناعي" icon="shield">
          <div className="stack">
            <Field label="نمط الظهور"><select className="select" disabled={!owner} value={f.privacy_mode} onChange={(e) => setF({ ...f, privacy_mode: e.target.value })}>
              <option value="private">خاص — العنوان محجوب حتى عن مسؤول النظام</option><option value="shared">مشترك</option></select></Field>
            <label className="check"><input type="checkbox" disabled={!owner} checked={f.ai_enabled} onChange={(e) => setF({ ...f, ai_enabled: e.target.checked })} />
              تفعيل الوكلاء والتحليل لهذا المشروع (إيقافه لا يمس الكتابة اليدوية إطلاقاً)</label>
            <div className="evidence">
              <div className="row between"><strong>نقل النص إلى مزود خارجي</strong>{activeConsent ? <span className="badge warn">مُفعّل</span> : <span className="badge ok">غير مسموح</span>}</div>
              <div className="dim">الوجهة الحالية: {provider?.destination} {provider?.external ? "— خارجية" : ""}</div>
              {provider?.retention_note && <div className="dim">{provider.retention_note}</div>}
              {owner && provider?.external && provider?.available && !activeConsent && (
                <button className="btn sm gold" style={{ marginTop: 6 }} onClick={() => confirm(`أوافق على إرسال مقاطع من المخطوط إلى ${provider.destination} عند تشغيل يطلب ذلك صراحةً؟`) &&
                  run(api(`/v1/projects/${pid}/consents`, { body: { kind: "external_ai", acknowledge_destination: provider.destination } }), "سُجلت الموافقة")}>منح الموافقة</button>
              )}
              {owner && activeConsent && <button className="btn sm danger" style={{ marginTop: 6 }} onClick={() => run(api(`/v1/projects/${pid}/consents/${activeConsent.id}`, { method: "DELETE" }), "أُلغيت الموافقة")}>سحب الموافقة</button>}
              {!provider?.external && <div className="dim" style={{ marginTop: 4 }}>لا حاجة لموافقة: لا يوجد مزود خارجي مضبوط.</div>}
            </div>
          </div>
        </Card>

        <WorldCalendars pid={pid!} canEdit={!!proj.data?.permissions?.includes("bible")} />

        <Card title="الأعضاء والأدوار">
          <table className="table"><tbody>{members.data?.items.map((m: any) => (
            <tr key={m.user_id}><td>{m.display_name}<div className="dim mono">{m.email}</div></td><td><span className="badge">{roleLabel(m.role)}</span></td>
              <td>{owner && m.role !== "owner" && <button className="btn sm ghost" onClick={() => run(api(`/v1/projects/${pid}/members/${m.user_id}`, { method: "DELETE" }), "أُزيل العضو")}>إزالة</button>}</td></tr>))}
          </tbody></table>
          {owner && (
            <div className="row" style={{ marginTop: 10 }}>
              <input className="input" style={{ flex: 1 }} dir="ltr" aria-label="بريد العضو" placeholder="email@example.com" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
              <select className="select" style={{ width: 150 }} aria-label="الدور" value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}>
                <option value="editor">محرر مشارك</option><option value="commenter">معلّق</option><option value="reader">قارئ تجريبي</option></select>
              <button className="btn" onClick={() => run(api(`/v1/projects/${pid}/members`, { body: invite }), "أُضيف العضو")}>إضافة</button>
            </div>
          )}
          <div className="dim" style={{ marginTop: 6 }}>المحرر المشارك يكتب ويقترح؛ قبول مقترحات الوكلاء والكانون والحذف لصاحب الرواية وحده.</div>
        </Card>

        <Card title="سلة المحذوفات">
          {!trash.data?.items.length ? <Empty title="السلة فارغة" /> : (
            <table className="table"><tbody>{trash.data.items.map((n: any) => (
              <tr key={n.id}><td>{n.title || n.type}</td><td className="dim">{when(n.deleted_at)}</td>
                <td><button className="btn sm" onClick={() => run(api(`/v1/nodes/${n.id}/restore`, { method: "POST" }), "استُعيد")}>استعادة</button></td></tr>))}
            </tbody></table>
          )}
        </Card>

        <Card title="بياناتك" icon="publish" className="span2">
          <div className="grid g2">
            <div className="stack">
              <strong>تصدير كامل البيانات</strong>
              <div className="dim">أرشيف ZIP مقروء: المخطوط، كل المراجعات، الكتاب المرجعي، المصادر الأصلية، الاستشهادات، المقترحات — مع بصمات SHA-256. يمكن استعادته في أي نسخة من «كاتب».</div>
              <button className="btn" disabled={!owner} onClick={() => download(`/v1/projects/${pid}/data-export`, "POST").catch(toast.error)}>تنزيل الأرشيف</button>
            </div>
            <div className="stack">
              <strong style={{ color: "var(--bad)" }}>حذف المشروع نهائياً</strong>
              <div className="dim">يحذف المشروع والمراجعات والمصادر والفهارس المشتقة فوراً. قد تبقى نسخ في النسخ الاحتياطية للخادم حتى انتهاء دورة الاحتفاظ المعلنة.</div>
              <input className="input" disabled={!owner} placeholder={`اكتب «${f.title}» للتأكيد`} value={confirmTitle} onChange={(e) => setConfirmTitle(e.target.value)} />
              <button className="btn danger" disabled={!owner || confirmTitle !== proj.data?.title}
                onClick={() => api(`/v1/projects/${pid}`, { method: "DELETE", body: { confirm_title: confirmTitle } }).then(() => { qc.invalidateQueries({ queryKey: ["projects"] }); nav("/"); }).catch(toast.error)}>حذف نهائي</button>
            </div>
          </div>
        </Card>
        <Card title="الموافقات المسجلة" className="span2">
          {!consents.data?.items.length ? <Empty title="لا موافقات" /> : (
            <table className="table"><tbody>{consents.data.items.map((c: any) => (
              <tr key={c.id}><td className="mono">{c.kind}</td><td>{c.scope.destination || c.scope.rights_basis}</td><td className="dim">{when(c.granted_at)}</td>
                <td>{c.revoked_at ? <Status value="cancelled" /> : <Status value="accepted" />}</td></tr>))}
            </tbody></table>
          )}
        </Card>
      </div>
    </>
  );
}


function WorldCalendars({ pid, canEdit }: { pid: string; canEdit: boolean }) {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery<{ custom: CalendarDef[] }>({ queryKey: ["calendars", pid], queryFn: () => api(`/v1/projects/${pid}/calendars`) });
  const [draft, setDraft] = useState({ id: "", name: "", suffix: "", epoch: "0", ratio: "1", months: "" });
  const save = async (list: CalendarDef[]) => {
    try {
      await api(`/v1/projects/${pid}/calendars`, { method: "PUT", body: { calendars: list } });
      qc.invalidateQueries({ queryKey: ["calendars", pid] });
      toast.ok("حُفظت تقاويم العالم الروائي");
    } catch (e) { toast.error(e); }
  };
  const list = q.data?.custom || [];
  const add = () => save([...list, { id: draft.id.trim(), name: draft.name.trim(), suffix: draft.suffix.trim(), epoch: Number(draft.epoch),
    ratio: Number(draft.ratio) || 1, months: draft.months.split(/[,،]/).map((x) => x.trim()).filter(Boolean) }])
    .then(() => setDraft({ id: "", name: "", suffix: "", epoch: "0", ratio: "1", months: "" }));
  return (
    <Card title="تقاويم العالم الروائي">
      <div className="dim" style={{ marginBottom: 8 }}>لعوالم متخيلة بتقويمها الخاص. كل تقويم يُسقط على محور زمن القصة: «سنة 1» = نقطة البداية، و«النسبة» = طول السنة على المحور.</div>
      {!list.length ? <Empty title="لا تقاويم مخصصة" /> : (
        <table className="table"><tbody>{list.map((c) => (
          <tr key={c.id}><td><strong>{c.name}</strong> <span className="mono dim">{c.id}</span><div className="dim">{c.months.join("، ")}</div></td>
            <td className="mono">سنة 1 = {c.epoch} · ×{c.ratio}</td>
            <td>{canEdit && <button className="btn sm ghost" onClick={() => save(list.filter((x) => x.id !== c.id))}>حذف</button>}</td></tr>))}
        </tbody></table>
      )}
      {canEdit && (
        <div className="form-grid" style={{ marginTop: 10 }}>
          <Field label="المعرّف (لاتيني)"><input className="input" dir="ltr" value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} placeholder="flood" /></Field>
          <Field label="الاسم"><input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="تقويم الطوفان" /></Field>
          <Field label="لاحقة السنة"><input className="input" value={draft.suffix} onChange={(e) => setDraft({ ...draft, suffix: e.target.value })} placeholder="ط" /></Field>
          <Field label="سنة 1 على المحور"><input className="input" dir="ltr" type="number" value={draft.epoch} onChange={(e) => setDraft({ ...draft, epoch: e.target.value })} /></Field>
          <Field label="طول السنة (نسبة)"><input className="input" dir="ltr" type="number" step="any" min="0.01" value={draft.ratio} onChange={(e) => setDraft({ ...draft, ratio: e.target.value })} /></Field>
          <Field label="الأشهر (افصل بفاصلة)"><input className="input" value={draft.months} onChange={(e) => setDraft({ ...draft, months: e.target.value })} placeholder="الندى، الريح، الملح" /></Field>
          <div className="full"><button className="btn" disabled={!draft.id || !draft.name} onClick={add}>إضافة تقويم</button></div>
        </div>
      )}
    </Card>
  );
}
