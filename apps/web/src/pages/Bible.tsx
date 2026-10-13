import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Character, EventItem, Fact, Place, TreeNode } from "../api/types";
import { useProject } from "../App";
import { HijriPicker } from "../components/HijriPicker";
import { Icon } from "../components/Icon";
import { Card, Empty, Field, Modal, Status, Tabs, useToast } from "../components/ui";

type Tab = "characters" | "places" | "events" | "facts";

export function BiblePage() {
  const [tab, setTab] = useState<Tab>("characters");
  return (
    <>
      <div className="page-head">
        <div className="grow"><div className="eyebrow">ذاكرة الرواية</div><h1>الكتاب المرجعي للرواية</h1>
          <div className="muted">الشخصيات والأماكن والأحداث والحقائق: الكانون المعتمد منفصل عن المسودة والفرضية والمصدر الخارجي.</div></div>
      </div>
      <Tabs value={tab} onChange={setTab} items={[["characters", "الشخصيات"], ["places", "الأماكن"], ["events", "الأحداث"], ["facts", "الحقائق والذاكرة"]]} />
      {tab === "characters" && <Characters />}
      {tab === "places" && <Places />}
      {tab === "events" && <Events />}
      {tab === "facts" && <Facts />}
    </>
  );
}

function useList<T>(kind: string) {
  const { pid } = useParams();
  return useQuery<{ items: T[] }>({ queryKey: [kind, pid], queryFn: () => api(`/v1/projects/${pid}/${kind}`) });
}

function useSave(kind: string, onDone?: () => void) {
  const { pid } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, body, method }: { id?: string; body?: any; method?: string }) =>
      api(`/v1/projects/${pid}/${kind}${id ? `/${id}` : ""}`, { method: method || (id ? "PATCH" : "POST"), body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [kind, pid] }); onDone?.(); toast.ok("حُفظ"); },
    onError: toast.error,
  });
}

const CHAR_FIELDS: [string, string][] = [
  ["role", "الدور"], ["birth_year", "سنة الميلاد (زمن القصة)"], ["death_year", "سنة الوفاة"], ["goal", "الهدف"],
  ["obstacle", "العائق"], ["secret", "السر"], ["arc", "قوس التحول"], ["description", "وصف"],
];

function Characters() {
  const q = useList<Character>("characters");
  const proj = useProject();
  const can = proj.data?.permissions?.includes("bible");
  const [edit, setEdit] = useState<Partial<Character> | null>(null);
  const save = useSave("characters", () => setEdit(null));
  return (
    <Card title={`الشخصيات (${q.data?.items.length ?? 0})`} icon="user"
      actions={can && <button className="btn primary sm" onClick={() => setEdit({ canonical_name: "", aliases: [], profile: {} })}><Icon name="plus" size={14} /> شخصية</button>}>
      {!q.data?.items.length ? <Empty title="لا شخصيات بعد" /> : (
        <table className="table"><thead><tr><th>الاسم</th><th>الكنى</th><th>الدور</th><th>الميلاد/الوفاة</th><th>الهدف</th><th>قوس التحول</th></tr></thead>
          <tbody>{q.data.items.map((c) => (
            <tr key={c.id} className="clickable" onClick={() => can && setEdit(c)}>
              <td><strong>{c.canonical_name}</strong></td><td className="dim">{c.aliases.join("، ")}</td><td>{c.profile.role}</td>
              <td className="mono">{c.profile.birth_year ?? "—"} / {c.profile.death_year ?? "—"}</td>
              <td>{c.profile.goal}</td><td>{c.profile.arc}</td>
            </tr>))}
          </tbody></table>
      )}
      {edit && (
        <Modal title={edit.id ? `تحرير: ${edit.canonical_name}` : "شخصية جديدة"} onClose={() => setEdit(null)}
          footer={<>
            {edit.id && <button className="btn danger" onClick={() => confirm("حذف الشخصية؟") && save.mutate({ id: edit.id, method: "DELETE" })}>حذف</button>}
            <span style={{ flex: 1 }} />
            <button className="btn primary" onClick={() => save.mutate({
              id: edit.id, body: {
                canonical_name: edit.canonical_name, aliases: edit.aliases,
                profile: Object.fromEntries(Object.entries(edit.profile || {}).map(([k, v]) => [k, (k.endsWith("_year") && v !== "" && v !== null) ? Number(v) : v])),
              },
            })} disabled={!edit.canonical_name}>حفظ</button></>}>
          <div className="form-grid">
            <Field label="الاسم المعتمد"><input className="input" value={edit.canonical_name} onChange={(e) => setEdit({ ...edit, canonical_name: e.target.value })} /></Field>
            <Field label="الكنى والأسماء البديلة (افصل بفاصلة)">
              <input className="input" value={(edit.aliases || []).join("، ")} onChange={(e) => setEdit({ ...edit, aliases: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean) })} />
            </Field>
            {CHAR_FIELDS.map(([k, label]) => (
              <Field key={k} label={label} full={["description", "arc"].includes(k)}>
                <input className="input" dir={k.endsWith("_year") ? "ltr" : undefined} type={k.endsWith("_year") ? "number" : "text"}
                  value={edit.profile?.[k] ?? ""} onChange={(e) => setEdit({ ...edit, profile: { ...edit.profile, [k]: e.target.value } })} />
              </Field>
            ))}
          </div>
        </Modal>
      )}
    </Card>
  );
}

function Places() {
  const q = useList<Place>("places");
  const proj = useProject();
  const can = proj.data?.permissions?.includes("bible");
  const [edit, setEdit] = useState<Partial<Place> | null>(null);
  const save = useSave("places", () => setEdit(null));
  return (
    <Card title={`الأماكن (${q.data?.items.length ?? 0})`} icon="map"
      actions={can && <button className="btn primary sm" onClick={() => setEdit({ name: "", aliases: [], profile: {} })}><Icon name="plus" size={14} /> مكان</button>}>
      {!q.data?.items.length ? <Empty title="لا أماكن بعد" /> : (
        <table className="table"><thead><tr><th>المكان</th><th>الوصف</th><th>القيود التاريخية</th><th>الإحداثيات</th></tr></thead>
          <tbody>{q.data.items.map((p) => (
            <tr key={p.id} className="clickable" onClick={() => can && setEdit(p)}>
              <td><strong>{p.name}</strong></td><td>{p.profile.description}</td><td>{p.profile.constraints}</td>
              <td className="mono">{p.lat !== null ? `${p.lat}, ${p.lon}` : "—"}</td></tr>))}
          </tbody></table>
      )}
      {edit && (
        <Modal title={edit.id ? `تحرير: ${edit.name}` : "مكان جديد"} onClose={() => setEdit(null)}
          footer={<>{edit.id && <button className="btn danger" onClick={() => save.mutate({ id: edit.id, method: "DELETE" })}>حذف</button>}<span style={{ flex: 1 }} />
            <button className="btn primary" disabled={!edit.name} onClick={() => save.mutate({ id: edit.id, body: {
              name: edit.name, aliases: edit.aliases, profile: edit.profile,
              lat: edit.lat === null || edit.lat === undefined || (edit.lat as any) === "" ? null : Number(edit.lat),
              lon: edit.lon === null || edit.lon === undefined || (edit.lon as any) === "" ? null : Number(edit.lon),
            } })}>حفظ</button></>}>
          <div className="form-grid">
            <Field label="الاسم"><input className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="أسماء بديلة"><input className="input" value={(edit.aliases || []).join("، ")} onChange={(e) => setEdit({ ...edit, aliases: e.target.value.split(/[,،]/).map((s) => s.trim()).filter(Boolean) })} /></Field>
            <Field label="الوصف" full><textarea className="input" value={edit.profile?.description || ""} onChange={(e) => setEdit({ ...edit, profile: { ...edit.profile, description: e.target.value } })} /></Field>
            <Field label="القيود التاريخية" full><input className="input" value={edit.profile?.constraints || ""} onChange={(e) => setEdit({ ...edit, profile: { ...edit.profile, constraints: e.target.value } })} /></Field>
            <Field label="خط العرض (اختياري)"><input className="input" dir="ltr" value={edit.lat ?? ""} onChange={(e) => setEdit({ ...edit, lat: e.target.value as any })} /></Field>
            <Field label="خط الطول (اختياري)"><input className="input" dir="ltr" value={edit.lon ?? ""} onChange={(e) => setEdit({ ...edit, lon: e.target.value as any })} /></Field>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function Events() {
  const { pid } = useParams();
  const q = useList<EventItem>("events");
  const chars = useList<Character>("characters");
  const places = useList<Place>("places");
  const tree = useQuery<any>({ queryKey: ["tree", pid], queryFn: () => api(`/v1/projects/${pid}/tree`) });
  const nodes: TreeNode[] = (tree.data?.manuscripts?.[0]?.nodes || []).filter((n: TreeNode) => n.type !== "part");
  const proj = useProject();
  const can = proj.data?.permissions?.includes("bible");
  const [edit, setEdit] = useState<Partial<EventItem> | null>(null);
  const save = useSave("events", () => setEdit(null));
  const name = (id: string) => chars.data?.items.find((c) => c.id === id)?.canonical_name || "؟";
  const num = (v: any) => (v === "" || v === null || v === undefined ? null : Number(v));
  const sorted = [...(q.data?.items || [])].sort((a, b) => (a.story_time_start ?? 1e9) - (b.story_time_start ?? 1e9));
  return (
    <Card title={`الأحداث (${q.data?.items.length ?? 0})`} icon="timeline"
      actions={can && <button className="btn primary sm" onClick={() => setEdit({ title: "", participant_ids: [], uncertainty: "exact", kind: "event" })}><Icon name="plus" size={14} /> حدث</button>}>
      {!sorted.length ? <Empty title="لا أحداث بعد" /> : (
        <table className="table"><thead><tr><th>زمن القصة</th><th>الحدث</th><th>اليقين</th><th>ترتيب السرد</th><th>المشاركون</th></tr></thead>
          <tbody>{sorted.map((e) => (
            <tr key={e.id} className="clickable" onClick={() => can && setEdit(e)}>
              <td className="mono">{e.story_time_start ?? "؟"}{e.story_time_end ? `–${e.story_time_end}` : ""} <span className="dim">{e.time_label}</span></td>
              <td><strong>{e.title}</strong> {e.kind !== "event" && <span className="badge">{({ birth: "ميلاد", death: "وفاة", travel: "سفر" } as any)[e.kind]}</span>}<div className="dim">{e.summary}</div></td>
              <td><span className="badge">{({ exact: "دقيق", approx: "تقريبي", range: "نطاق", unknown: "مجهول" } as any)[e.uncertainty]}</span></td>
              <td className="mono">{e.narration_order ?? "—"}</td>
              <td>{e.participant_ids.map(name).join("، ")}</td>
            </tr>))}
          </tbody></table>
      )}
      {edit && (
        <Modal title={edit.id ? `تحرير: ${edit.title}` : "حدث جديد"} onClose={() => setEdit(null)} wide
          footer={<>{edit.id && <button className="btn danger" onClick={() => save.mutate({ id: edit.id, method: "DELETE" })}>حذف</button>}<span style={{ flex: 1 }} />
            <button className="btn primary" disabled={!edit.title} onClick={() => {
              const body: any = { title: edit.title, summary: edit.summary || "", story_time_start: num(edit.story_time_start), story_time_end: num(edit.story_time_end),
                time_label: edit.time_label || "", uncertainty: edit.uncertainty, narration_order: num(edit.narration_order), kind: edit.kind,
                participant_ids: edit.participant_ids || [], node_id: edit.node_id || null, place_id: edit.place_id || null };
              if (edit.id) body.clear = ["story_time_start", "story_time_end", "node_id", "place_id", "narration_order"].filter((k) => body[k] === null);
              save.mutate({ id: edit.id, body });
            }}>حفظ</button></>}>
          <div className="form-grid">
            <Field label="العنوان" full><input className="input" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
            <Field label="النوع"><select className="select" value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>
              <option value="event">حدث</option><option value="birth">ميلاد</option><option value="death">وفاة</option><option value="travel">سفر</option></select></Field>
            <Field label="درجة اليقين الزمني"><select className="select" value={edit.uncertainty} onChange={(e) => setEdit({ ...edit, uncertainty: e.target.value })}>
              <option value="exact">دقيق</option><option value="approx">تقريبي</option><option value="range">نطاق</option><option value="unknown">مجهول</option></select></Field>
            <Field label="بداية (سنة القصة)"><input className="input" dir="ltr" type="number" step="any" value={edit.story_time_start ?? ""} onChange={(e) => setEdit({ ...edit, story_time_start: e.target.value as any })} /></Field>
            <Field label="نهاية (اختياري)"><input className="input" dir="ltr" type="number" step="any" value={edit.story_time_end ?? ""} onChange={(e) => setEdit({ ...edit, story_time_end: e.target.value as any })} /></Field>
            <Field label="وصف الزمن"><input className="input" value={edit.time_label || ""} onChange={(e) => setEdit({ ...edit, time_label: e.target.value })} /></Field>
            <div className="full"><HijriPicker onConvert={(c) => setEdit({ ...edit, story_time_start: c.story_time, time_label: c.label, uncertainty: c.uncertainty })} /></div>
            <Field label="ترتيب السرد"><input className="input" dir="ltr" type="number" value={edit.narration_order ?? ""} onChange={(e) => setEdit({ ...edit, narration_order: e.target.value as any })} /></Field>
            <Field label="المشهد المرتبط"><select className="select" value={edit.node_id || ""} onChange={(e) => setEdit({ ...edit, node_id: e.target.value || null })}>
              <option value="">—</option>{nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}</select></Field>
            <Field label="المكان"><select className="select" value={edit.place_id || ""} onChange={(e) => setEdit({ ...edit, place_id: e.target.value || null })}>
              <option value="">—</option>{places.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
            <Field label="المشاركون" full>
              <div className="pill-list">{chars.data?.items.map((c) => {
                const on = edit.participant_ids?.includes(c.id);
                return <button type="button" key={c.id} className={`btn sm ${on ? "gold" : ""}`} onClick={() => setEdit({ ...edit,
                  participant_ids: on ? edit.participant_ids!.filter((x) => x !== c.id) : [...(edit.participant_ids || []), c.id] })}>{c.canonical_name}</button>;
              })}</div>
            </Field>
            <Field label="ملخص" full><textarea className="input" value={edit.summary || ""} onChange={(e) => setEdit({ ...edit, summary: e.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function Facts() {
  const { pid } = useParams();
  const q = useList<Fact>("facts");
  const chars = useList<Character>("characters");
  const proj = useProject();
  const qc = useQueryClient();
  const toast = useToast();
  const owner = proj.data?.permissions?.includes("approve_canon");
  const can = proj.data?.permissions?.includes("bible");
  const [edit, setEdit] = useState<any>(null);
  const save = useSave("facts", () => setEdit(null));
  const act = async (url: string, method = "POST") => {
    try { await api(url, { method }); qc.invalidateQueries({ queryKey: ["facts", pid] }); } catch (e) { toast.error(e); }
  };
  const groups: [string, string][] = [["canon", "الكانون المعتمد"], ["draft", "مسودة"], ["hypothesis", "فرضيات"], ["external", "مصادر خارجية"]];
  return (
    <div className="grid g2">
      <Card title="كيف تعمل الذاكرة السببية" icon="shield" className="span2">
        <div className="muted">كل حقيقة لها حالة معرفية. الانتقال إلى <strong>الكانون</strong> فعل بشري يقوم به صاحب الرواية وحده؛ لا تُستنتج حقائق معتمدة من مقترحات لم تُقبل. الحقائق الخارجية المتعارضة تُعرض جنباً إلى جنب دون حسم آلي.</div>
        {can && <button className="btn primary sm" style={{ marginTop: 8 }} onClick={() => setEdit({ predicate: "", subject_type: "character", epistemic_status: "draft", object: { value: "" } })}><Icon name="plus" size={14} /> حقيقة</button>}
      </Card>
      {groups.map(([st, label]) => {
        const items = q.data?.items.filter((f) => f.epistemic_status === st) || [];
        return (
          <Card key={st} title={<>{label} <span className="badge">{items.length}</span></>}>
            {!items.length ? <Empty title="—" /> : (
              <div className="stack" style={{ gap: 6 }}>{items.map((f) => (
                <div key={f.id} className="card" style={{ padding: 8 }}>
                  <div className="row between">
                    <span><strong>{f.subject_label || chars.data?.items.find((c) => c.id === f.subject_id)?.canonical_name || "العالم"}</strong> · {f.predicate}: <span className="mono">{String(f.object?.value ?? "")}</span></span>
                    <Status value={f.epistemic_status} />
                  </div>
                  {f.statement && <div className="dim">{f.statement}</div>}
                  <div className="row" style={{ marginTop: 4 }}>
                    <span className="badge">{f.origin === "agent" ? "من مقترح وكيل" : "يدوي"}</span>
                    {owner && st !== "canon" && <button className="btn sm gold" onClick={() => act(`/v1/projects/${pid}/facts/${f.id}/approve`)}>اعتماد في الكانون</button>}
                    {owner && st === "canon" && <button className="btn sm" onClick={() => act(`/v1/projects/${pid}/facts/${f.id}?status=draft`, "PATCH")}>إرجاع لمسودة</button>}
                    {can && <button className="btn sm ghost" onClick={() => act(`/v1/projects/${pid}/facts/${f.id}`, "DELETE")}>حذف</button>}
                  </div>
                </div>))}
              </div>
            )}
          </Card>
        );
      })}
      {edit && (
        <Modal title="حقيقة جديدة" onClose={() => setEdit(null)}
          footer={<button className="btn primary" disabled={!edit.predicate} onClick={() => save.mutate({ body: {
            ...edit, subject_id: edit.subject_id || null,
            object: { value: edit.object.value !== "" && !isNaN(Number(edit.object.value)) ? Number(edit.object.value) : edit.object.value },
          } })}>حفظ</button>}>
          <div className="form-grid">
            <Field label="الموضوع (شخصية)"><select className="select" value={edit.subject_id || ""} onChange={(e) => setEdit({ ...edit, subject_id: e.target.value, subject_label: chars.data?.items.find((c) => c.id === e.target.value)?.canonical_name || "" })}>
              <option value="">العالم الروائي</option>{chars.data?.items.map((c) => <option key={c.id} value={c.id}>{c.canonical_name}</option>)}</select></Field>
            <Field label="الخاصية"><input className="input" value={edit.predicate} onChange={(e) => setEdit({ ...edit, predicate: e.target.value })} placeholder="birth_year، لون العينين…" /></Field>
            <Field label="القيمة"><input className="input" value={edit.object.value} onChange={(e) => setEdit({ ...edit, object: { value: e.target.value } })} /></Field>
            <Field label="الحالة المعرفية"><select className="select" value={edit.epistemic_status} onChange={(e) => setEdit({ ...edit, epistemic_status: e.target.value })}>
              <option value="draft">مسودة</option><option value="hypothesis">فرضية</option><option value="external">مصدر خارجي</option></select></Field>
            <Field label="الصياغة" full><input className="input" value={edit.statement || ""} onChange={(e) => setEdit({ ...edit, statement: e.target.value })} /></Field>
          </div>
        </Modal>
      )}
    </div>
  );
}
