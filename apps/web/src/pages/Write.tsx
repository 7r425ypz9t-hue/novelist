import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mark, mergeAttributes } from "@tiptap/core";
import Highlight from "@tiptap/extension-highlight";
import TextAlign from "@tiptap/extension-text-align";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Character, Doc, Place, Proposal, Revision, TreeNode } from "../api/types";
import { useProject } from "../App";
import { Icon } from "../components/Icon";
import { HijriPicker } from "../components/HijriPicker";
import { DiffView, Empty, Field, Modal, Status, Tabs, useToast } from "../components/ui";
import { ago, arabicPattern, countWords, docText, findSpans, fmt, type SearchOpts } from "../lib/arabic";
import { SAVE_LABEL, useAutosave } from "../lib/autosave";
import { journalClear, journalGet } from "../lib/offline";

/* Footnote mark (FR04 حواشٍ): the note travels with the text and is rendered as real notes in every export. */
const Footnote = Mark.create({
  name: "footnote",
  inclusive: false,
  addAttributes() {
    return { note: { default: "", parseHTML: (el) => el.getAttribute("data-note"), renderHTML: (a) => ({ "data-note": a.note, title: a.note }) } };
  },
  parseHTML() { return [{ tag: "span[data-footnote]" }]; },
  renderHTML({ HTMLAttributes }) { return ["span", mergeAttributes(HTMLAttributes, { "data-footnote": "", class: "fn-mark" }), 0]; },
});

const EXTENSIONS = [
  StarterKit.configure({ code: false, codeBlock: false, link: false, heading: { levels: [1, 2, 3] } }),
  TextAlign.configure({ types: ["heading", "paragraph"] }),
  Highlight,
  Footnote,
];

export function WritePage() {
  const { pid, nodeId } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const project = useProject();
  const canWrite = !!project.data?.permissions?.includes("write");
  const tree = useQuery<any>({ queryKey: ["tree", pid], queryFn: () => api(`/v1/projects/${pid}/tree`) });
  const nodes: TreeNode[] = tree.data?.manuscripts?.[0]?.nodes || [];
  const manuscriptId: string | undefined = tree.data?.manuscripts?.[0]?.manuscript?.id;
  const current = nodes.find((n) => n.id === nodeId) || null;
  const [doc, setDoc] = useState<Doc | null>(null);
  const [hideL, setHideL] = useState(false);
  const [hideR, setHideR] = useState(false);
  const [live, setLive] = useState(0);
  const [modal, setModal] = useState<null | "find" | "footnote" | "checkpoint">(null);
  // a manuscript-wide search hit in another unit: select it once that unit's document is loaded
  const jumpRef = useRef<{ docId: string; q: string; opts: SearchOpts; index: number } | null>(null);

  useEffect(() => {
    if (!nodeId && nodes.length) {
      const first = nodes.find((n) => n.document_id && n.type === "scene") || nodes.find((n) => n.document_id);
      if (first) nav(`/p/${pid}/write/${first.id}`, { replace: true });
    }
  }, [nodeId, nodes, nav, pid]);

  const onSynced = useCallback((d: Doc) => {
    setDoc((prev) => (prev && prev.id === d.id ? { ...prev, version: d.version, word_count: d.word_count, current_revision_id: d.current_revision_id } : prev));
    qc.invalidateQueries({ queryKey: ["revisions", d.id] });
  }, [qc]);
  const saver = useAutosave(doc, onSynced);

  const editor = useEditor({
    extensions: EXTENSIONS,
    textDirection: "auto",
    editable: false,
    shouldRerenderOnTransaction: true,
    editorProps: { attributes: { "aria-label": "محرر النص", spellcheck: "true", lang: "ar" } },
    onUpdate: ({ editor: ed, transaction }) => {
      if (!transaction.docChanged) return;
      setLive(countWords(docText(ed.getJSON())));
      saver.change(ed.getJSON());
    },
  });

  // load the document of the selected node (flushing pending saves of the previous one first)
  useEffect(() => {
    let cancelled = false;
    // lock the editor while switching units: keystrokes in this window would land in the previous unit
    editor?.setEditable(false);
    (async () => {
      await saver.flush();
      if (!current?.document_id) { setDoc(null); return; }
      const d = await api<Doc>(`/v1/documents/${current.document_id}`);
      if (cancelled || !editor) return;
      const pending = await journalGet(d.id);
      let content = d.content_json;
      if (pending) {
        if (pending.baseVersion === d.version) {
          content = pending.content;
          toast.info("استُعيدت تعديلات محلية لم تُزامن بعد، وستُرسل الآن.");
        } else {
          toast.info("وُجدت تعديلات محلية على نسخة أقدم؛ ستظهر شاشة حل التعارض.");
        }
      }
      setDoc(d);
      editor.commands.setContent(content, { emitUpdate: false });
      editor.setEditable(canWrite);
      setLive(countWords(docText(content)));
      const j = jumpRef.current;
      if (j && j.docId === d.id) {
        jumpRef.current = null;
        const re = arabicPattern(j.q, j.opts);
        const m = re ? editorMatches(editor, re)[j.index] : undefined;
        if (m) requestAnimationFrame(() => editor.chain().focus().setTextSelection(m).scrollIntoView().run());
      }
      if (pending) {
        if (pending.baseVersion === d.version) saver.change(content);
        else saver.change(pending.content);
      }
    })().catch(toast.error);
    return () => { cancelled = true; };
  }, [current?.document_id, editor, canWrite]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); setModal("checkpoint"); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") { e.preventDefault(); setModal("find"); }
      if ((e.ctrlKey || e.metaKey) && e.key === ".") { e.preventDefault(); setHideL((v) => !v); setHideR((v) => !v); }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const [tone, label] = SAVE_LABEL[saver.state];
  const btn = (icon: string, title: string, run: () => void, active = false) => (
    <button className={`btn ghost icon ${active ? "active" : ""}`} title={title} aria-label={title} aria-pressed={active}
      onMouseDown={(e) => e.preventDefault()} onClick={run} disabled={!canWrite}
      style={active ? { color: "var(--gold)", background: "var(--gold-soft)" } : undefined}>
      <Icon name={icon} size={16} />
    </button>
  );

  return (
    <div className={`write ${hideL ? "hide-left" : ""} ${hideR ? "hide-right" : ""}`}>
      <aside className="pane tree" aria-label="شجرة المخطوط">
        <TreePane nodes={nodes} pid={pid!} manuscriptId={manuscriptId} activeId={nodeId} canWrite={canWrite}
          onFlush={saver.flush} />
      </aside>

      <section className="editor-col">
        <div className="editor-toolbar" role="toolbar" aria-label="أدوات التحرير">
          <button className="btn ghost icon" title="إظهار/إخفاء الشجرة" onClick={() => setHideL(!hideL)}><Icon name="panelR" size={16} /></button>
          <span className="sep" />
          {editor && <>
            {btn("undo", "تراجع", () => editor.chain().focus().undo().run())}
            {btn("redo", "إعادة", () => editor.chain().focus().redo().run())}
            <span className="sep" />
            {btn("bold", "عريض", () => editor.chain().focus().toggleBold().run(), editor.isActive("bold"))}
            {btn("italic", "مائل", () => editor.chain().focus().toggleItalic().run(), editor.isActive("italic"))}
            {btn("heading", "عنوان فرعي", () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive("heading"))}
            {btn("quote", "اقتباس", () => editor.chain().focus().toggleBlockquote().run(), editor.isActive("blockquote"))}
            {btn("footnote", "حاشية", () => setModal("footnote"), editor.isActive("footnote"))}
            <span className="sep" />
            {btn("rtl", "اتجاه الفقرة: يمين-يسار", () => editor.chain().focus().setTextDirection("rtl").run())}
            {btn("ltr", "اتجاه الفقرة: يسار-يمين", () => editor.chain().focus().setTextDirection("ltr").run())}
            <span className="sep" />
            {btn("find", "بحث واستبدال (Ctrl+F)", () => setModal("find"))}
            {btn("history", "نقطة حفظ مسماة (Ctrl+S)", () => setModal("checkpoint"))}
          </>}
          <span style={{ flex: 1 }} />
          {current && <span className="dim crumb">{current.label}</span>}
          <button className="btn ghost icon" title="إظهار/إخفاء الأدوات" onClick={() => setHideR(!hideR)}><Icon name="panelL" size={16} /></button>
        </div>

        {saver.conflict && (
          <div className="alert bad" style={{ margin: 10 }}>
            <strong>تعارض نسخة:</strong> حُفظت نسخة أحدث من مكان آخر. لن يُكتب فوق أي نسخة — اختر:
            <div className="row" style={{ marginTop: 8 }}>
              <ConflictDiff local={saver.conflict.local} server={saver.conflict.server.content_json} />
              <button className="btn" onClick={() => saver.resolve("mine")}>اعتماد نسختي كمراجعة جديدة (تبقى الأخرى في السجل)</button>
              <button className="btn" onClick={async () => {
                const s = await saver.resolve("theirs");
                if (s && editor) { editor.commands.setContent(s.content_json, { emitUpdate: false }); setDoc(s); }
              }}>تحميل نسخة الخادم</button>
            </div>
          </div>
        )}

        <div className="editor-scroll">
          {current?.document_id ? (
            <div className="paper" dir="rtl">
              <h1 style={{ fontFamily: "var(--font-text)", textAlign: "center", color: "var(--gold)", marginBottom: 24, fontSize: 24 }}>
                {current.title || current.label}
              </h1>
              <EditorContent editor={editor} />
            </div>
          ) : (
            <Empty title={nodes.length ? "اختر فصلاً أو مشهداً من الشجرة" : "المخطوط فارغ"}>
              {nodes.length ? null : "أضف فصلاً من الشجرة لتبدأ الكتابة."}
            </Empty>
          )}
        </div>

        <footer className="statusbar" aria-live="polite">
          <span className="row" style={{ gap: 6 }} data-testid="save-state"><span className={`dot ${tone} ${saver.state === "syncing" ? "pulse" : ""}`} />{label}</span>
          <span>آخر مزامنة: {ago(saver.lastSynced)}</span>
          <span style={{ flex: 1 }} />
          {!canWrite && <span className="badge warn">قراءة فقط — دورك لا يسمح بالتحرير</span>}
          <span className="num" data-testid="live-words">{fmt(live)} كلمة</span>
          {doc && <span className="mono">v{doc.version}</span>}
          <span className="kbd">Ctrl+.</span><span className="dim">وضع التركيز</span>
        </footer>
      </section>

      <aside className="pane tools" aria-label="أدوات المشهد">
        {current && <ToolsPane node={current} doc={doc} pid={pid!} canWrite={canWrite}
          onRestored={(d) => { setDoc(d); saver.setVersion(d.version); editor?.commands.setContent(d.content_json, { emitUpdate: false }); journalClear(d.id); }} />}
      </aside>

      {modal === "footnote" && editor && <FootnoteModal onClose={() => setModal(null)} onSave={(note) => {
        if (editor.state.selection.empty) { toast.info("حدّد الكلمة أو العبارة التي تتعلق بها الحاشية أولاً."); return; }
        editor.chain().focus().setMark("footnote", { note }).run();
        setModal(null);
      }} />}
      {modal === "find" && editor && <FindReplace editor={editor} currentNodeId={nodeId} onClose={() => setModal(null)}
        onJump={(hit, q, opts, index) => {
          setModal(null);
          if (hit.node_id === nodeId) {
            const re = arabicPattern(q, opts);
            const m = re ? editorMatches(editor, re)[index] : undefined;
            if (m) editor.chain().focus().setTextSelection(m).scrollIntoView().run();
          } else { jumpRef.current = { docId: hit.document_id, q, opts, index }; nav(`/p/${pid}/write/${hit.node_id}`); }
        }} />}
      {modal === "checkpoint" && editor && <CheckpointModal onClose={() => setModal(null)} onSave={async (lbl) => {
        try { await saver.checkpoint(editor.getJSON(), lbl); toast.ok("حُفظت نقطة مراجعة مسماة"); setModal(null); } catch (e) { toast.error(e); }
      }} />}
    </div>
  );
}

function ConflictDiff({ local, server }: { local: any; server: any }) {
  const [open, setOpen] = useState(false);
  const segs = useMemo(() => simpleDiff(docText(server), docText(local)), [local, server]);
  return (
    <>
      <button className="btn" onClick={() => setOpen(true)}>عرض الفروق</button>
      {open && <Modal title="الفروق: نسخة الخادم ← نسختي" wide onClose={() => setOpen(false)}><DiffView segs={segs} /></Modal>}
    </>
  );
}

function simpleDiff(a: string, b: string) {
  // paragraph-level client diff for the conflict screen (server diff covers saved revisions)
  const pa = a.split("\n\n"), pb = b.split("\n\n");
  const out: { op: "equal" | "insert" | "delete"; text: string }[] = [];
  const max = Math.max(pa.length, pb.length);
  for (let i = 0; i < max; i++) {
    if (pa[i] === pb[i]) out.push({ op: "equal", text: (pa[i] || "") + "\n\n" });
    else {
      if (pa[i] !== undefined) out.push({ op: "delete", text: pa[i] + "\n\n" });
      if (pb[i] !== undefined) out.push({ op: "insert", text: pb[i] + "\n\n" });
    }
  }
  return out;
}

/* ───────────── tree ───────────── */

function TreePane({ nodes, pid, manuscriptId, activeId, canWrite, onFlush }: {
  nodes: TreeNode[]; pid: string; manuscriptId?: string; activeId?: string; canWrite: boolean; onFlush: () => Promise<void>;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const [drag, setDrag] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["tree", pid] }); qc.invalidateQueries({ queryKey: ["dashboard", pid] }); };
  const add = useMutation({
    mutationFn: (b: { type: string; parent_id?: string | null; title: string }) =>
      api<TreeNode>(`/v1/projects/${pid}/nodes`, { body: { ...b, manuscript_id: manuscriptId } }),
    onSuccess: (n) => { refresh(); nav(`/p/${pid}/write/${n.id}`); },
    onError: toast.error,
  });
  const move = useMutation({
    mutationFn: (b: { id: string; parent_id: string | null; position: number }) =>
      api(`/v1/nodes/${b.id}/reorder`, { method: "PATCH", body: { parent_id: b.parent_id, position: b.position } }),
    onSuccess: refresh, onError: toast.error,
  });
  const trash = useMutation({
    mutationFn: (id: string) => api(`/v1/nodes/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.ok("نُقل إلى سلة المحذوفات — يمكن استعادته من الإعدادات"); refresh(); nav(`/p/${pid}/write`); },
    onError: toast.error,
  });
  const rename = useMutation({
    mutationFn: (b: { id: string; title: string }) => api(`/v1/nodes/${b.id}`, { method: "PATCH", body: { title: b.title } }),
    onSuccess: refresh, onError: toast.error,
  });
  const active = nodes.find((n) => n.id === activeId);
  const chapterOfActive = active ? (active.type === "chapter" ? active : nodes.find((n) => n.id === active.parent_id)) : null;

  const onDrop = (target: TreeNode) => (e: DragEvent) => {
    e.preventDefault();
    setOver(null);
    const src = nodes.find((n) => n.id === drag);
    if (!src || src.id === target.id) return;
    if (src.type === "scene" && target.type === "chapter") move.mutate({ id: src.id, parent_id: target.id, position: 0 });
    else if (src.type === target.type) move.mutate({ id: src.id, parent_id: target.parent_id, position: target.position });
  };
  const indent = (n: TreeNode) => (n.type === "scene" ? 22 : n.type === "chapter" && n.parent_id ? 12 : 0);

  return (
    <div style={{ padding: 10 }}>
      <div className="row between" style={{ marginBottom: 8 }}>
        <strong>المخطوط</strong>
        {canWrite && (
          <div className="row" style={{ gap: 4 }}>
            <button className="btn sm" onClick={() => add.mutate({ type: "chapter", title: "" })} title="فصل جديد">+ فصل</button>
            <button className="btn sm" disabled={!chapterOfActive} title="مشهد في الفصل الحالي"
              onClick={() => chapterOfActive && add.mutate({ type: "scene", parent_id: chapterOfActive.id, title: "" })}>+ مشهد</button>
            <button className="btn sm ghost" onClick={() => add.mutate({ type: "part", title: "جزء جديد" })} title="جزء">+ جزء</button>
            <button className="btn sm ghost" onClick={() => setImporting(true)} title="استيراد DOCX/MD/TXT">استيراد</button>
          </div>
        )}
      </div>
      {!nodes.length && <Empty title="لا فصول بعد" />}
      <div role="tree" aria-label="فصول ومشاهد">
        {nodes.map((n) => (
          <div key={n.id} role="treeitem" aria-selected={n.id === activeId}
            className={`tree-node ${n.id === activeId ? "active" : ""} ${over === n.id ? "drop" : ""}`}
            style={{ paddingInlineStart: 8 + indent(n), fontWeight: n.type === "scene" ? 400 : 600 }}
            draggable={canWrite && n.type !== "part"}
            onDragStart={() => setDrag(n.id)} onDragOver={(e) => { e.preventDefault(); setOver(n.id); }}
            onDragLeave={() => setOver(null)} onDrop={onDrop(n)}
            onClick={async () => { if (n.document_id) { await onFlush(); nav(`/p/${pid}/write/${n.id}`); } }}
            onDoubleClick={() => {
              if (!canWrite) return;
              const t = prompt("العنوان الجديد", n.title);
              if (t !== null) rename.mutate({ id: n.id, title: t });
            }}>
            <Icon name={n.type === "scene" ? "file" : n.type === "chapter" ? "bible" : "projects"} size={14} />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {n.title || n.label}
            </span>
            {n.type !== "part" && <span className="wc">{fmt(n.word_count)}</span>}
          </div>
        ))}
      </div>
      {canWrite && active && (
        <button className="btn sm danger" style={{ marginTop: 12 }}
          onClick={() => confirm(`نقل «${active.title || active.label}» وما تحته إلى سلة المحذوفات؟ لا يُحذف أي سجل مراجعات.`) && trash.mutate(active.id)}>
          <Icon name="trash" size={14} /> نقل المحدد إلى السلة
        </button>
      )}
      <p className="dim" style={{ marginTop: 10 }}>اسحب المشاهد بين الفصول لإعادة الترتيب؛ تبقى المعرفات ثابتة. انقر مرتين لإعادة التسمية.</p>
      {importing && <ImportModal pid={pid} manuscriptId={manuscriptId} onClose={() => setImporting(false)} onDone={() => { setImporting(false); refresh(); }} />}
    </div>
  );
}

/* ───────────── tools pane ───────────── */

function ToolsPane({ node, doc, pid, canWrite, onRestored }: {
  node: TreeNode; doc: Doc | null; pid: string; canWrite: boolean; onRestored: (d: Doc) => void;
}) {
  const [tab, setTab] = useState<"matrix" | "history" | "proposals" | "notes">("matrix");
  return (
    <div style={{ padding: 10 }}>
      <Tabs value={tab} onChange={setTab} items={[["matrix", "المصفوفة"], ["history", "المراجعات"], ["proposals", "المقترحات"], ["notes", "تعليقات"]]} />
      {tab === "matrix" && <SceneMatrix key={node.id} node={node} pid={pid} canWrite={canWrite} />}
      {tab === "history" && doc && <History doc={doc} canWrite={canWrite} onRestored={onRestored} />}
      {tab === "proposals" && doc && <DocProposals doc={doc} pid={pid} />}
      {tab === "notes" && doc && <Comments doc={doc} />}
    </div>
  );
}

function SceneMatrix({ node, pid, canWrite }: { node: TreeNode; pid: string; canWrite: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const chars = useQuery<{ items: Character[] }>({ queryKey: ["characters", pid], queryFn: () => api(`/v1/projects/${pid}/characters`) });
  const places = useQuery<{ items: Place[] }>({ queryKey: ["places", pid], queryFn: () => api(`/v1/projects/${pid}/places`) });
  const [m, setM] = useState<Record<string, any>>({ ...node.meta });
  const [status, setStatus] = useState(node.status);
  const save = useMutation({
    mutationFn: () => api(`/v1/nodes/${node.id}`, { method: "PATCH", body: {
      status, meta: { ...m, story_time: m.story_time === "" || m.story_time === undefined ? null : Number(m.story_time) } } }),
    onSuccess: () => { toast.ok("حُفظت مصفوفة المشهد"); qc.invalidateQueries({ queryKey: ["tree", pid] }); },
    onError: toast.error,
  });
  const set = (k: string) => (e: { target: { value: string } }) => setM({ ...m, [k]: e.target.value });
  const ta = (k: string, label: string) => (
    <Field label={label}><textarea className="input" style={{ minHeight: 56 }} value={m[k] || ""} onChange={set(k)} disabled={!canWrite} /></Field>
  );
  return (
    <div className="stack">
      <div className="dim">مصفوفة المشهد (FR10) — تغذي فحوص البنية والاستمرارية.</div>
      <Field label="الحالة">
        <select className="select" value={status} onChange={(e) => setStatus(e.target.value)} disabled={!canWrite}>
          <option value="idea">فكرة</option><option value="draft">مسودة</option><option value="revised">منقّح</option><option value="final">نهائي</option>
        </select>
      </Field>
      {ta("goal", "الهدف")}
      {ta("conflict", "الصراع")}
      {ta("outcome", "النتيجة")}
      {ta("new_information", "المعلومة الجديدة")}
      <Field label="شخصية التبئير (POV)">
        <select className="select" value={m.pov_character_id || ""} onChange={set("pov_character_id")} disabled={!canWrite}>
          <option value="">—</option>{chars.data?.items.map((c) => <option key={c.id} value={c.id}>{c.canonical_name}</option>)}
        </select>
      </Field>
      <Field label="المكان">
        <select className="select" value={m.place_id || ""} onChange={set("place_id")} disabled={!canWrite}>
          <option value="">—</option>{places.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </Field>
      <div className="form-grid">
        <Field label="زمن القصة (سنة)"><input className="input" type="number" step="any" dir="ltr" value={m.story_time ?? ""} onChange={set("story_time")} disabled={!canWrite} /></Field>
        <Field label="وصف الزمن"><input className="input" value={m.story_time_label || ""} onChange={set("story_time_label")} placeholder="ربيع، فجر…" disabled={!canWrite} /></Field>
      </div>
      <HijriPicker disabled={!canWrite} onConvert={(c) => setM({ ...m, story_time: c.story_time, story_time_label: c.label })} />
      {canWrite && <button className="btn primary" onClick={() => save.mutate()} disabled={save.isPending}>حفظ المصفوفة</button>}
    </div>
  );
}

function History({ doc, canWrite, onRestored }: { doc: Doc; canWrite: boolean; onRestored: (d: Doc) => void }) {
  const toast = useToast();
  const q = useQuery<{ items: Revision[] }>({ queryKey: ["revisions", doc.id], queryFn: () => api(`/v1/documents/${doc.id}/revisions?limit=100`) });
  const [diff, setDiff] = useState<any>(null);
  const compare = async (r: Revision) => {
    try { setDiff({ rev: r, data: await api(`/v1/documents/${doc.id}/diff?a=${r.id}`) }); } catch (e) { toast.error(e); }
  };
  const restore = async (r: Revision) => {
    try {
      const d = await api<Doc>(`/v1/revisions/${r.id}/restore`, { method: "POST", headers: { "If-Match": `W/"${doc.version}"` } });
      toast.ok(`استُعيدت المراجعة #${r.revision_no} كمراجعة جديدة — لم يُحذف شيء من السجل`);
      setDiff(null);
      onRestored(d);
      q.refetch();
    } catch (e) { toast.error(e); }
  };
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="dim">كل حفظ مراجعة ثابتة لا تُعدّل (بصمة SHA-256). الاستعادة تُنشئ مراجعة جديدة.</div>
      {q.data?.items.map((r) => (
        <div key={r.id} className="card" style={{ padding: 8 }}>
          <div className="row between">
            <span className="mono">#{r.revision_no}</span>
            <span className="badge">{({ autosave: "حفظ تلقائي", checkpoint: "نقطة حفظ", restore: "استعادة", proposal: "مقترح مقبول", import: "استيراد" } as any)[r.kind] || r.kind}</span>
            <span className="dim">{ago(r.created_at)}</span>
          </div>
          {r.label && <div style={{ fontSize: 13 }}>{r.label}</div>}
          <div className="row between">
            <span className="dim num">{fmt(r.word_count)} كلمة{r.author_type === "human_accepted_ai" ? " · تعديل مقترح قَبِله المؤلف" : ""}</span>
            <button className="btn sm" onClick={() => compare(r)}>قارن بالحالية</button>
          </div>
        </div>
      ))}
      {diff && (
        <Modal title={`المراجعة #${diff.rev.revision_no} ← النسخة الحالية`} wide onClose={() => setDiff(null)}
          footer={canWrite ? <button className="btn gold" onClick={() => restore(diff.rev)}>استعادة هذه المراجعة</button> : undefined}>
          <div className="row" style={{ marginBottom: 8 }}>
            <span className="badge ok">+{diff.data.stats.inserted_words} كلمة</span>
            <span className="badge bad">−{diff.data.stats.deleted_words} كلمة</span>
          </div>
          <DiffView segs={diff.data.segments} />
        </Modal>
      )}
    </div>
  );
}

function DocProposals({ doc, pid }: { doc: Doc; pid: string }) {
  const q = useQuery<{ items: Proposal[] }>({ queryKey: ["proposals", pid, "doc", doc.id], queryFn: () => api(`/v1/projects/${pid}/proposals?state=pending&document_id=${doc.id}`) });
  if (!q.data?.items.length) return <Empty title="لا مقترحات معلقة لهذه الوحدة" />;
  return (
    <div className="stack" style={{ gap: 6 }}>
      {q.data.items.map((p) => (
        <div key={p.id} className="card" style={{ padding: 8 }}>
          <div className="row between"><span className="mono">{p.agent_id}/{p.skill_id}</span><Status value={p.certainty} /></div>
          <div style={{ fontSize: 13 }}>{p.title}</div>
        </div>
      ))}
      <Link className="btn sm" to={`/p/${pid}/proposals`}>مراجعة واتخاذ القرار في غرفة النقد</Link>
    </div>
  );
}

function Comments({ doc }: { doc: Doc }) {
  const q = useQuery<any>({ queryKey: ["comments", doc.id], queryFn: () => api(`/v1/documents/${doc.id}/comments`) });
  const [body, setBody] = useState("");
  const toast = useToast();
  const add = async () => {
    try { await api(`/v1/documents/${doc.id}/comments`, { body: { body } }); setBody(""); q.refetch(); } catch (e) { toast.error(e); }
  };
  return (
    <div className="stack">
      {q.data?.items.map((c: any) => (
        <div key={c.id} className="card" style={{ padding: 8 }}><div className="row between"><strong>{c.author}</strong><span className="dim">{ago(c.created_at)}</span></div><div>{c.body}</div></div>
      ))}
      <textarea className="input" value={body} onChange={(e) => setBody(e.target.value)} placeholder="ملاحظة للمؤلف أو المحرر…" />
      <button className="btn" disabled={!body.trim()} onClick={add}>إضافة تعليق</button>
    </div>
  );
}

/* ───────────── modals ───────────── */

function ImportModal({ pid, manuscriptId, onClose, onDone }: { pid: string; manuscriptId?: string; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [preview, setPreview] = useState<{ filename: string; chapters: { title: string; text: string; words: number }[]; total_words: number } | null>(null);
  const [keep, setKeep] = useState<boolean[]>([]);
  const load = async (f: File) => {
    const fd = new FormData();
    fd.append("file", f);
    try {
      const p = await api<any>(`/v1/projects/${pid}/import/preview`, { form: fd });
      setPreview(p);
      setKeep(p.chapters.map(() => true));
    } catch (e) { toast.error(e); }
  };
  const commit = async () => {
    if (!preview) return;
    try {
      const chapters = preview.chapters.filter((_, i) => keep[i]).map(({ title, text }) => ({ title, text }));
      await api(`/v1/projects/${pid}/import/commit`, { body: { manuscript_id: manuscriptId, chapters } });
      toast.ok(`استُورد ${chapters.length} فصلاً — كل فصل يبدأ بمراجعة «استيراد»`);
      onDone();
    } catch (e) { toast.error(e); }
  };
  return (
    <Modal title="استيراد مخطوط (DOCX · MD · TXT)" wide onClose={onClose}
      footer={preview ? <><span className="dim">{fmt(preview.total_words)} كلمة</span><span style={{ flex: 1 }} /><button className="btn primary" disabled={!keep.some(Boolean)} onClick={commit}>استيراد المحدد</button></> : undefined}>
      {!preview ? (
        <Field label="اختر الملف — تُكتشف الفصول من العناوين («الفصل …»، أنماط Heading، #)"><input className="input" type="file" accept=".docx,.md,.txt" onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} /></Field>
      ) : (
        <table className="table"><thead><tr><th /><th>الفصل المكتشف</th><th>الكلمات</th><th>البداية</th></tr></thead>
          <tbody>{preview.chapters.map((c, i) => (
            <tr key={i}><td><input type="checkbox" checked={keep[i]} onChange={(e) => setKeep(keep.map((k, j) => (j === i ? e.target.checked : k)))} aria-label={`تضمين ${c.title}`} /></td>
              <td><input className="input" value={c.title} onChange={(e) => setPreview({ ...preview, chapters: preview.chapters.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)) })} /></td>
              <td className="mono">{fmt(c.words)}</td><td className="dim" style={{ fontFamily: "var(--font-text)" }}>{c.text.slice(0, 90)}…</td></tr>))}
          </tbody></table>
      )}
    </Modal>
  );
}

function FootnoteModal({ onClose, onSave }: { onClose: () => void; onSave: (note: string) => void }) {
  const [note, setNote] = useState("");
  return (
    <Modal title="إضافة حاشية للعبارة المحددة" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>إلغاء</button><button className="btn primary" disabled={!note.trim()} onClick={() => onSave(note)}>إضافة</button></>}>
      <textarea className="input" autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="نص الحاشية — يظهر حاشيةً مرقّمة في DOCX/PDF/EPUB" />
    </Modal>
  );
}

function CheckpointModal({ onClose, onSave }: { onClose: () => void; onSave: (label: string) => void }) {
  const [label, setLabel] = useState("");
  return (
    <Modal title="نقطة حفظ مسماة" onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>إلغاء</button><button className="btn primary" onClick={() => onSave(label || "نقطة حفظ")}>حفظ</button></>}>
      <Field label="وصف المراجعة"><input className="input" autoFocus value={label} onChange={(e) => setLabel(e.target.value)} placeholder="مثلاً: قبل إعادة كتابة النهاية" /></Field>
    </Modal>
  );
}

type Range = { from: number; to: number };
type SearchHit = { node_id: string; document_id: string; label: string; title: string; count: number;
  snippets: { before: string; match: string; after: string; cut_before: boolean; cut_after: boolean }[] };

/* Matches inside each paragraph across formatting boundaries (bold/footnote runs split text nodes). */
function editorMatches(editor: any, re: RegExp): Range[] {
  const out: Range[] = [];
  editor.state.doc.descendants((node: any, pos: number) => {
    if (!node.isTextblock) return true;
    let text = "";
    const at: number[] = [];
    node.forEach((child: any, off: number) => {
      const t = child.isText ? child.text : "\uFFFC";
      for (let i = 0; i < t.length; i++) at.push(pos + 1 + off + i);
      text += t;
    });
    for (const h of findSpans(re, text)) out.push({ from: at[h.start], to: at[h.end - 1] + 1 });
    return false;
  });
  return out;
}

function FindReplace({ editor, currentNodeId, onClose, onJump }: {
  editor: any; currentNodeId?: string; onClose: () => void;
  onJump: (hit: SearchHit, q: string, opts: SearchOpts, index: number) => void;
}) {
  const { pid } = useParams();
  const [scope, setScope] = useState<"unit" | "all">("unit");
  const [find, setFind] = useState("");
  const [repl, setRepl] = useState("");
  const [opts, setOpts] = useState<Required<SearchOpts>>({ ignoreMarks: true, unifyLetters: true, wholeWord: false, clitics: true });
  const [k, setK] = useState(0);
  const toast = useToast();
  const re = useMemo(() => arabicPattern(find, opts), [find, opts]);
  const matches = useMemo(() => (re ? editorMatches(editor, re) : []), [re, editor.state.doc]); // eslint-disable-line react-hooks/exhaustive-deps
  const [submitted, setSubmitted] = useState<{ q: string; opts: SearchOpts } | null>(null);
  const all = useQuery<{ total: number; units: number; items: SearchHit[] }>({
    queryKey: ["ms-search", pid, submitted],
    enabled: !!submitted,
    queryFn: () => api(`/v1/projects/${pid}/manuscript/search?` + new URLSearchParams({
      q: submitted!.q, ignore_marks: String(submitted!.opts.ignoreMarks), unify_letters: String(submitted!.opts.unifyLetters),
      whole_word: String(submitted!.opts.wholeWord), clitics: String(submitted!.opts.clitics) })),
  });
  const goto = (i: number) => {
    if (!matches.length) return;
    const j = (i + matches.length) % matches.length;
    setK(j);
    editor.chain().setTextSelection(matches[j]).scrollIntoView().run();
  };
  const replaceOne = () => {
    const m = matches[k % Math.max(1, matches.length)];
    if (!m) return;
    (repl ? editor.chain().insertContentAt(m, { type: "text", text: repl }) : editor.chain().deleteRange(m)).run();
  };
  const replaceAll = () => {
    if (!matches.length) return;
    const tr = editor.state.tr;
    [...matches].reverse().forEach((m) => (repl ? tr.insertText(repl, m.from, m.to) : tr.delete(m.from, m.to)));
    editor.view.dispatch(tr);
    toast.ok(`استُبدل ${matches.length} موضعاً (يمكن التراجع)`);
  };
  const opt = (key: keyof SearchOpts, label: string, disabled = false) => (
    <label className="check"><input type="checkbox" checked={opts[key]} disabled={disabled} onChange={(e) => { setOpts({ ...opts, [key]: e.target.checked }); setK(0); }} /> {label}</label>
  );
  const searchAll = () => { if (find.trim()) setSubmitted({ q: find.trim(), opts: { ...opts } }); };
  return (
    <Modal title="بحث واستبدال" wide onClose={onClose}
      footer={scope === "unit" ? <>
        <span className="dim" aria-live="polite">{matches.length ? `${k + 1} من ${matches.length}` : "لا نتائج"}</span>
        <button className="btn" disabled={!matches.length} onClick={() => goto(k - 1)}>السابق</button>
        <button className="btn" disabled={!matches.length} onClick={() => goto(k + 1)}>التالي</button>
        <button className="btn" disabled={!matches.length || !editor.isEditable} onClick={replaceOne}>استبدال هذا</button>
        <button className="btn primary" disabled={!matches.length || !editor.isEditable} onClick={replaceAll}>استبدال الكل</button>
      </> : <>
        <span className="dim" aria-live="polite">{all.data ? `${all.data.total} موضعاً في ${all.data.units} وحدة` : ""}</span>
        <button className="btn primary" disabled={!find.trim() || all.isFetching} onClick={searchAll}>ابحث في المخطوط</button>
      </>}>
      <Tabs value={scope} onChange={setScope} items={[["unit", "في هذه الوحدة"], ["all", "في كامل المخطوط"]]} />
      <div className="form-grid">
        <Field label="ابحث عن"><input className="input" autoFocus value={find}
          onChange={(e) => { setFind(e.target.value); setK(0); }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); scope === "all" ? searchAll() : goto(e.shiftKey ? k - 1 : k + (matches.length && editor.state.selection.from === matches[k]?.from ? 1 : 0)); } }} /></Field>
        {scope === "unit" && <Field label="استبدل بـ"><input className="input" value={repl} onChange={(e) => setRepl(e.target.value)} /></Field>}
        <div className="row full" style={{ flexWrap: "wrap", gap: 14 }}>
          {opt("ignoreMarks", "تجاهل التشكيل والتطويل")}
          {opt("unifyLetters", "توحيد الهمزات والتاء المربوطة والألف المقصورة والأرقام")}
          {opt("wholeWord", "كلمة كاملة")}
          {opt("clitics", "مع السوابق المتصلة (و، ف، ب، ك، ل، ال)", !opts.wholeWord)}
        </div>
      </div>
      {scope === "all" && (
        <div className="stack scroll-y" style={{ maxHeight: "48vh", marginTop: 10, gap: 8 }}>
          {all.isError && <div className="alert bad">تعذّر البحث</div>}
          {all.data && !all.data.items.length && <Empty title="لا نتائج في المخطوط" />}
          {all.data?.items.map((h) => (
            <div key={h.node_id} className="evidence">
              <div className="row between"><strong>{h.label || h.title || "وحدة"}{h.title && h.label && ` — ${h.title}`}</strong>
                <span className="row">{h.node_id === currentNodeId && <span className="badge info">الوحدة الحالية</span>}<span className="badge">{h.count}</span></span></div>
              {h.snippets.map((sn, i) => (
                <button key={i} className="find-hit" onClick={() => onJump(h, submitted!.q, submitted!.opts, i)}>
                  {sn.cut_before && "…"}{sn.before}<mark>{sn.match}</mark>{sn.after}{sn.cut_after && "…"}
                </button>
              ))}
              {h.count > h.snippets.length && <div className="dim">و{h.count - h.snippets.length} موضعاً آخر في هذه الوحدة</div>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
