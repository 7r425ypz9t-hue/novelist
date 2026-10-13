/* Mirrors apps/api/nis/text.py so the live editor count equals the server count. */
const TASHKEEL = /[ؐ-ًؚ-ٰٟۖ-ۭ]/g;
const WORD = /[\p{L}\p{N}]+(?:['’][\p{L}\p{N}]+)*/gu;

export function stripDiacritics(s: string) {
  return s.replace(TASHKEEL, "").replace(/ـ/g, "");
}

export function countWords(s: string) {
  return (stripDiacritics(s).match(WORD) || []).length;
}

const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
export function arNum(n: number | string) {
  return String(n).replace(/[0-9]/g, (d) => AR_DIGITS[Number(d)]);
}

export function fmt(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(n);
}

export function when(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return new Intl.DateTimeFormat("ar", { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export function ago(iso: string | null | undefined) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("ar", { numeric: "auto" });
  if (s < 60) return rtf.format(-Math.round(s), "second");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}

export function docText(doc: any): string {
  const walk = (n: any): string => {
    if (!n) return "";
    if (n.type === "text") return n.text || "";
    if (n.type === "hardBreak") return "\n";
    return (n.content || []).map(walk).join(n.type === "doc" ? "\n\n" : "");
  };
  return walk(doc);
}

/* Arabic-aware literal search — mirrors apps/api/nis/text.py → arabic_pattern (keep the two in step). */
const MARKS = "[\\u0610-\\u061A\\u064B-\\u065F\\u0670\\u06D6-\\u06ED\\u0640]*";
const LOOSE: Record<string, string> = {};
for (const g of ["اأإآٱ", "يىئ", "هة", "وؤ"]) for (const c of g) LOOSE[c] = `[${g}]`;
for (let d = 0; d < 10; d++) {
  const cls = `[${d}${"٠١٢٣٤٥٦٧٨٩"[d]}${"۰۱۲۳۴۵۶۷۸۹"[d]}]`;
  LOOSE[String(d)] = LOOSE["٠١٢٣٤٥٦٧٨٩"[d]] = LOOSE["۰۱۲۳۴۵۶۷۸۹"[d]] = cls;
}
const esc = (c: string) => c.replace(/[.*+?^${}()|[\]\\/-]/g, "\\$&");

export type SearchOpts = { ignoreMarks?: boolean; unifyLetters?: boolean; wholeWord?: boolean };

export function arabicPattern(query: string, { ignoreMarks = true, unifyLetters = true, wholeWord = false }: SearchOpts = {}): RegExp | null {
  const q = (ignoreMarks ? stripDiacritics(query) : query).trim();
  if (!q) return null;
  const parts = [...q].map((c) => (/\s/.test(c) ? "[^\\S\\n]+" : unifyLetters ? LOOSE[c] ?? esc(c) : esc(c)));
  let body = parts.join(ignoreMarks ? MARKS : "") + (ignoreMarks ? MARKS : "");
  if (wholeWord) body = `(?<![\\p{L}\\p{N}])${body}(?![\\p{L}\\p{N}])`;
  return new RegExp(body, "giu");
}
