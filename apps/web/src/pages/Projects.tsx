import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Project } from "../api/types";
import { roleLabel } from "../App";
import { Icon } from "../components/Icon";
import { Card, Empty, Field, Loading, Modal, useToast } from "../components/ui";
import { ago, fmt } from "../lib/arabic";

export function ProjectsPage() {
  const q = useQuery<{ items: Project[] }>({ queryKey: ["projects"], queryFn: () => api("/v1/projects") });
  const [open, setOpen] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const qc = useQueryClient();
  const nav = useNavigate();
  const restore = useMutation({
    mutationFn: (f: File) => { const fd = new FormData(); fd.append("file", f); return api("/v1/projects/import", { form: fd }); },
    onSuccess: (r: any) => { toast.ok("استُعيد المشروع بعد التحقق من سلامة الأرشيف"); qc.invalidateQueries({ queryKey: ["projects"] }); nav(`/p/${r.id}`); },
    onError: toast.error,
  });
  return (
    <>
      <div className="page-head">
        <div className="grow">
          <div className="eyebrow">PROJECTS</div>
          <h1>مشاريعك الروائية</h1>
        </div>
        <input ref={file} type="file" accept=".zip" hidden onChange={(e) => e.target.files?.[0] && restore.mutate(e.target.files[0])} />
        <button className="btn" onClick={() => file.current?.click()}><Icon name="upload" size={16} /> استعادة أرشيف</button>
        <button className="btn primary" onClick={() => setOpen(true)}><Icon name="plus" size={16} /> مشروع جديد</button>
      </div>
      {q.isLoading ? <Loading /> : !q.data?.items.length ? (
        <Card><Empty title="لا مشاريع بعد">ابدأ مشروعك الأول: عنوان ونوع ووصف قصير، ثم انتقل إلى غرفة الكتابة.</Empty></Card>
      ) : (
        <div className="grid g3">
          {q.data.items.map((p) => (
            <Link key={p.id} to={`/p/${p.id}`} className="card" style={{ color: "inherit", textDecoration: "none" }}>
              <div className="card-b stack" style={{ gap: 6 }}>
                <div className="row between">
                  <h2>{p.title}</h2>
                  <span className="badge">{roleLabel(p.role)}</span>
                </div>
                <div className="muted" style={{ minHeight: 44 }}>{p.logline || p.description || <span className="dim">بلا وصف</span>}</div>
                <div className="row between dim">
                  <span>{p.genre || "—"}</span>
                  <span className="num">{fmt(p.words || 0)} كلمة{p.word_goal ? ` / ${fmt(p.word_goal)}` : ""}</span>
                </div>
                {p.word_goal > 0 && <div className="meter"><span style={{ width: `${Math.min(100, ((p.words || 0) / p.word_goal) * 100)}%` }} /></div>}
                <div className="dim">آخر تحديث {ago(p.updated_at)}</div>
              </div>
            </Link>
          ))}
        </div>
      )}
      {open && <NewProject onClose={() => setOpen(false)} />}
    </>
  );
}

function NewProject({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ title: "", genre: "", logline: "", description: "", word_goal: 80000, author_name: "", privacy_mode: "private" });
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api<Project>("/v1/projects", { body: f }),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ["projects"] }); onClose(); nav(`/p/${p.id}`); },
    onError: toast.error,
  });
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: k === "word_goal" ? Number(e.target.value) : e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal title="مشروع روائي جديد" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>إلغاء</button><button className="btn primary" form="np" disabled={!f.title || m.isPending}>إنشاء</button></>}>
      <form id="np" className="form-grid" onSubmit={submit}>
        <Field label="عنوان الرواية" full><input className="input" required autoFocus value={f.title} onChange={set("title")} /></Field>
        <Field label="النوع الأدبي"><input className="input" value={f.genre} onChange={set("genre")} placeholder="رواية تاريخية، اجتماعية…" /></Field>
        <Field label="اسم المؤلف على الغلاف"><input className="input" value={f.author_name} onChange={set("author_name")} /></Field>
        <Field label="الجملة المحورية (logline)" full><input className="input" value={f.logline} onChange={set("logline")} /></Field>
        <Field label="وصف موجز" full><textarea className="input" value={f.description} onChange={set("description")} /></Field>
        <Field label="هدف الكلمات"><input className="input" type="number" min={0} value={f.word_goal} onChange={set("word_goal")} /></Field>
        <Field label="نمط الظهور">
          <select className="select" value={f.privacy_mode} onChange={set("privacy_mode")}>
            <option value="private">خاص — حتى مسؤول النظام لا يرى العنوان</option>
            <option value="shared">مشترك مع المتعاونين</option>
          </select>
        </Field>
      </form>
    </Modal>
  );
}
