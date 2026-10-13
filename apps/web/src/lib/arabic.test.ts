import { describe, expect, it } from "vitest";
import { arabicPattern, countWords, findSpans } from "./arabic";

// Same cases as apps/api/tests/test_text.py — the editor and the server must agree.
describe("Arabic word count", () => {
  it.each([
    ["ذهبَ الولدُ إلى المدرسةِ", 4],
    ["وقالــت: «نعم»، ثم مضت.", 4],
    ["في عام 1958 افتُتح الميناء", 5],
    ["He said مرحباً yesterday", 4],
    ["،،، ... !!", 0],
    ["٢٠٢٦ سنة", 2],
  ])("%s → %i", (text, n) => {
    expect(countWords(text)).toBe(n);
  });
});

describe("arabicPattern (mirror of nis.text.arabic_pattern)", () => {
  const text = "قالَ إنّ الحياةَ قصيرةٌ، ثمّ إنتهى في عام ١٩٥٨ والمدرسـة.";
  const hits = (q: string, o = {}) => findSpans(arabicPattern(q, o)!, text).map((m) => m.text);
  it("ignores tashkeel/tatweel and unifies letter forms and digits", () => {
    expect(hits("الحياة")).toEqual(["الحياةَ"]);
    expect(hits("قصيره")).toEqual(["قصيرةٌ"]);
    expect(hits("1958")).toEqual(["١٩٥٨"]);
    expect(hits("المدرسة")).toEqual(["المدرسـة"]);
  });
  it("supports whole-word and strict modes and treats input literally", () => {
    expect(hits("ان", { wholeWord: true })).toEqual(["إنّ"]);
    expect(hits("ان", { unifyLetters: false })).toEqual([]);
    expect(hits("(.*)+")).toEqual([]);
    expect(arabicPattern("  ")).toBeNull();
  });
});

describe("whole word with proclitics", () => {
  it("matches «وقصيرة», «بالقصيرة» but not «مقصيرة», prefix outside the match", () => {
    const text = "قصيرةٌ وقصيرة بالقصيرة فالقصيرة مقصيرة";
    const spans = findSpans(arabicPattern("قصيرة", { wholeWord: true })!, text);
    expect(spans.map((m) => m.text)).toEqual(["قصيرةٌ", "قصيرة", "قصيرة", "قصيرة"]);
    expect(text[spans[1].start - 1]).toBe("و");
    expect(findSpans(arabicPattern("قصيرة", { wholeWord: true, clitics: false })!, text).length).toBe(1);
  });
});
