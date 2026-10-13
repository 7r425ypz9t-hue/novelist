import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import { useToast } from "./ui";

export interface Converted { story_time: number; label: string; uncertainty: string; note: string; gregorian: string }

const MONTHS = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"];

/** Enter a date in the Hijri calendar; the story axis stays Gregorian-decimal, the author's wording stays in the label. */
export function HijriPicker({ onConvert, disabled }: { onConvert: (c: Converted) => void; disabled?: boolean }) {
  const { pid } = useParams();
  const toast = useToast();
  const [y, setY] = useState("");
  const [m, setM] = useState("");
  const [d, setD] = useState("");
  const go = async () => {
    const q = new URLSearchParams({ calendar: "hijri", year: y });
    if (m) q.set("month", m);
    if (m && d) q.set("day", d);
    try {
      const c = await api<Converted>(`/v1/projects/${pid}/calendar/convert?${q}`);
      onConvert(c);
      toast.info(`${c.label} ← ${c.gregorian}. ${c.note}`);
    } catch (e) { toast.error(e); }
  };
  return (
    <div className="row" style={{ gap: 6 }}>
      <span className="dim">بالهجري:</span>
      <input className="input" style={{ width: 80 }} dir="ltr" type="number" placeholder="1377" aria-label="السنة الهجرية" value={y} onChange={(e) => setY(e.target.value)} disabled={disabled} />
      <select className="select" style={{ width: 120 }} aria-label="الشهر الهجري" value={m} onChange={(e) => setM(e.target.value)} disabled={disabled}>
        <option value="">— الشهر</option>{MONTHS.map((x, i) => <option key={x} value={i + 1}>{x}</option>)}
      </select>
      <input className="input" style={{ width: 64 }} dir="ltr" type="number" min={1} max={30} placeholder="يوم" aria-label="اليوم الهجري" value={d} onChange={(e) => setD(e.target.value)} disabled={disabled || !m} />
      <button type="button" className="btn sm" disabled={disabled || !y} onClick={go}>تحويل</button>
    </div>
  );
}
