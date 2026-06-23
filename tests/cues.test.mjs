import { test } from "node:test";
import assert from "node:assert/strict";
import { formatTimecode, reindex, splitCueAtChar, mergeCues }
  from "../src/titulkovac/web/static/cues.js";

test("formatTimecode -> SRT format", () => {
  assert.equal(formatTimecode(0), "00:00:00,000");
  assert.equal(formatTimecode(1), "00:00:01,000");
  assert.equal(formatTimecode(3661.5), "01:01:01,500");
  assert.equal(formatTimecode(-2), "00:00:00,000");
});

test("reindex renumbers 1-based", () => {
  const out = reindex([{ index: 9 }, { index: 3 }, { index: 5 }]);
  assert.deepEqual(out.map((c) => c.index), [1, 2, 3]);
});

test("splitCueAtChar splits text + time by char ratio", () => {
  const cue = { index: 1, start: 0, end: 10, text: "abcdefghij",
                translations: { en: "X" }, edited: false };
  const [a, b] = splitCueAtChar(cue, 5);
  assert.equal(a.text, "abcde");
  assert.equal(b.text, "fghij");
  assert.equal(a.start, 0);
  assert.equal(a.end, 5);
  assert.equal(b.start, 5);
  assert.equal(b.end, 10);
  assert.equal(a.edited, true);
  assert.equal(b.edited, true);
  assert.deepEqual(b.translations, {});
});

test("splitCueAtChar clamps out-of-range positions", () => {
  const cue = { index: 1, start: 0, end: 10, text: "abcde", translations: {} };
  const [a, b] = splitCueAtChar(cue, 0);
  assert.ok(a.text.length >= 1 && b.text.length >= 1);
});

test("mergeCues joins text/time/translations", () => {
  const a = { index: 1, start: 0, end: 2, text: "Ahoj", translations: { en: "Hi" } };
  const b = { index: 2, start: 2, end: 4, text: "svete", translations: { en: "world" } };
  const m = mergeCues(a, b);
  assert.equal(m.text, "Ahoj svete");
  assert.equal(m.start, 0);
  assert.equal(m.end, 4);
  assert.equal(m.translations.en, "Hi world");
  assert.equal(m.edited, true);
});
