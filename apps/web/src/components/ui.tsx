import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { DiffSeg, Evidence } from "../api/types";
import { Icon } from "./Icon";

export function Card({ title, actions, children, className = "", bodyClass = "card-b", icon }: {
  title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; icon?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title !== undefined && (
        <header className="card-h">
          {icon && <Icon name={icon} size={16} />}
          <h2 className="grow">{title}</h2>
          {actions}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, tone = "", progress }: {
  label: string; value: ReactNode; sub?: ReactNode; tone?: "" | "gold" | "bad" | "ok"; progress?: number | null;
}) {
  return (
    <div className={`card kpi ${tone}`}>
      <div className="label">{label}</div>
      <div className="value num">{value}</div>
      {sub && <div className="sub">{sub}</div>}
      {progress !== undefined && progress !== null && (
        <div className="meter" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${Math.min(100, progress * 100)}%` }} />
        </div>
      )}
    </div>
  );
}

const SEV: Record<string, [string, string]> = {
  high: ["bad", "عالٍ"], medium: ["warn", "متوسط"], low: ["info", "منخفض"],
  HIGH: ["bad", "مخاطرة عالية"], MEDIUM: ["warn", "مخاطرة متوسطة"], LOW: ["ok", "مخاطرة منخفضة"],
};
export function Severity({ level }: { level: string }) {
  const [tone, label] = SEV[level] || ["", level];
  return <span className={`badge ${tone}`}>{label}</span>;
}

const STATUS: Record<string, [string, string]> = {
  queued: ["info", "في الانتظار"], running: ["info", "قيد التشغيل"], succeeded: ["ok", "اكتمل"],
  failed: ["bad", "فشل"], cancelled: ["", "أُلغي"], pending: ["warn", "معلق"], accepted: ["ok", "مقبول"],
  rejected: ["", "مرفوض"], stale: ["bad", "متقادم"], open: ["warn", "مفتوح"], resolved: ["ok", "محلول"],
  waived: ["info", "مُعفى"], dismissed: ["", "مستبعد"], canon: ["gold", "كانون"], draft: ["info", "مسودة"],
  hypothesis: ["", "فرضية"], external: ["warn", "مصدر خارجي"], indexed: ["ok", "مفهرس"], done: ["ok", "جاهز"],
  supported: ["ok", "مدعوم"], inferred: ["info", "استنتاج"], speculative: ["", "تخميني"],
  objective: ["info", "موضوعي"], taste: ["gold", "ذوقي"],
};
export function Status({ value }: { value: string }) {
  const [tone, label] = STATUS[value] || ["", value];
  return <span className={`badge ${tone}`}>{label}</span>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>;
}

export function Modal({ title, onClose, children, wide, footer }: {
  title: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean; footer?: ReactNode;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`card modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true">
        <header className="card-h">
          <h2 className="grow">{title}</h2>
          <button className="btn ghost icon" onClick={onClose} aria-label="إغلاق"><Icon name="x" /></button>
        </header>
        <div className="card-b">{children}</div>
        {footer && <footer className="card-h" style={{ borderTop: "1px solid var(--line)", borderBottom: 0, justifyContent: "flex-end" }}>{footer}</footer>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: [T, ReactNode][];
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={value === k} className={`tab ${value === k ? "active" : ""}`} onClick={() => onChange(k)}>
          {label}
        </button>
      ))}
    </div>
  );
}

/* ── toasts ── */
type Toast = { id: number; tone: "ok" | "bad" | "info" | "warn"; text: string };
const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { ...t, id }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 5200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => <div key={t.id} className={`card toast alert ${t.tone}`}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  );
}
export function useToast() {
  const push = useContext(ToastCtx);
  return {
    ok: (text: string) => push({ tone: "ok", text }),
    info: (text: string) => push({ tone: "info", text }),
    error: (e: unknown) => push({ tone: "bad", text: e instanceof ApiError ? e.message : String((e as Error)?.message || e) }),
  };
}

/* ── diff & evidence ── */
export function DiffView({ segs }: { segs: DiffSeg[] }) {
  if (!segs.length) return <Empty title="لا فروق" />;
  return (
    <div className="diff" dir="rtl">
      {segs.map((s, i) => s.op === "insert" ? <ins key={i}>{s.text}</ins> : s.op === "delete" ? <del key={i}>{s.text}</del> : <span key={i}>{s.text}</span>)}
    </div>
  );
}

export function EvidenceList({ items, onOpen }: { items: Evidence[]; onOpen?: (e: Evidence) => void }) {
  if (!items?.length) return null;
  return (
    <div className="stack" style={{ gap: 6 }}>
      {items.map((e, i) => (
        <div key={i} className="evidence">
          <div className="row between">
            <span className="row" style={{ gap: 6 }}>
              <span className="badge">{e.kind === "text" ? "نص" : e.kind === "entity" ? "سجل" : e.kind === "source" ? "مصدر" : "موضع"}</span>
              <strong style={{ fontSize: 13 }}>{e.label || e.entity_type}</strong>
              {e.field && <span className="dim">{e.field}: <span className="mono">{String(e.value ?? "")}</span></span>}
              {e.epistemic_status && <Status value={e.epistemic_status} />}
            </span>
            {onOpen && e.document_id && <button className="btn sm" onClick={() => onOpen(e)}>افتح الشاهد</button>}
          </div>
          {e.excerpt && <div className="quote" style={{ marginTop: 6 }}>{e.excerpt}</div>}
          {e.note && <div className="dim" style={{ marginTop: 4 }}>{e.note}</div>}
        </div>
      ))}
    </div>
  );
}

export function Field({ label, children, full }: { label: string; children: ReactNode; full?: boolean }) {
  return <label className={`field ${full ? "full" : ""}`}>{label}{children}</label>;
}

export function Loading() {
  return <div className="empty"><span className="dot info pulse" /> جارٍ التحميل…</div>;
}
