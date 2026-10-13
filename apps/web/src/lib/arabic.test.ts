import { describe, expect, it } from "vitest";
import { countWords } from "./arabic";

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
