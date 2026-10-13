import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { useToast } from "./ui";

export interface Converted { story_time: number; label: string; uncertainty: string; note: string; gregorian: string | null }
export interface CalendarDef { id: string; name: string; suffix: string; epoch: number; ratio: number; months: string[] }

const HIJRI_MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"];

/** Enter story time in the Hijri calendar or in one of the novel's own world calendars. The story axis stays a
 *  single decimal line; the author's own wording is kept as the label. */
export function HijriPicker({ onConvert, disabled }: { onConvert: (c: Converted) => void; disabled?: boolean }) {
  const { pid } = useParams();
  const toast = useToast();
  const cals = useQuery<{ custom: CalendarDef[] }>({ queryKey: ["calendars", pid], queryFn: () => api(`/v1/projects/${pid}/calendars`) });
  const [cal, setCal] = useState("hijri");
  const [y, setY] = useState("");
  const [m, setM] = useState("");
  const [d, setD] = useState("");
  const custom = cals.data?.custom.find((c) => c.id === cal);
  const months = cal === "hijri" ? HIJRI_MONTHS : custom?.months || [];
  const go = async () => {
    const q = new URLSearchParams({ calendar: cal, year: y });
    if (m) q.set("month", m);
    if (cal === "hijri" && m && d) q.set("day", d);
    try {
      const c = await api<Converted>(`/v1/projects/${pid}/calendar/convert?${q}`);
      onConvert(c);
      toast.info(`${c.label}${c.gregorian ? ` ← ${c.gregorian}` : ""}. ${c.note}`);
    } catch (e) { toast.error(e); }
  };
  return (
    <div className="row" style={{ gap: 6 }}>
      <select className="select" style={{ width: 130 }} aria-label="التقويم" value={cal} disabled={disabled}
        onChange={(e) => { setCal(e.target.value); setM(""); setD(""); }}>
        <option value="hijri">الهجري</option>
        {cals.data?.custom.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <input className="input" style={{ width: 80 }} dir="ltr" type="number" placeholder="السنة" aria-label="السنة في التقويم" value={y} onChange={(e) => setY(e.target.value)} disabled={disabled} />
      {months.length > 0 && (
        <select className="select" style={{ width: 120 }} aria-label="الشهر في التقويم" value={m} onChange={(e) => setM(e.target.value)} disabled={disabled}>
          <option value="">— الشهر</option>{months.map((x, i) => <option key={x + i} value={i + 1}>{x}</option>)}
        </select>
      )}
      {cal === "hijri" && (
        <input className="input" style={{ width: 64 }} dir="ltr" type="number" min={1} max={30} placeholder="يوم" aria-label="اليوم في التقويم" value={d} onChange={(e) => setD(e.target.value)} disabled={disabled || !m} />
      )}
      <button type="button" className="btn sm" disabled={disabled || !y} onClick={go}>تحويل</button>
    </div>
  );
}
