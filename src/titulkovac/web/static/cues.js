// Čisté funkce pro práci s titulky. ŽÁDNÁ závislost na DOM -> testovatelné
// přes `node --test` i importovatelné v prohlížeči (<script type="module">).

export function formatTimecode(seconds) {
  if (seconds < 0) seconds = 0;
  let ms = Math.round(seconds * 1000);
  const h = Math.floor(ms / 3600000); ms -= h * 3600000;
  const m = Math.floor(ms / 60000); ms -= m * 60000;
  const s = Math.floor(ms / 1000); ms -= s * 1000;
  const p = (n, w) => String(n).padStart(w, "0");
  return `${p(h, 2)}:${p(m, 2)}:${p(s, 2)},${p(ms, 3)}`;
}

export function reindex(cues) {
  return cues.map((c, i) => ({ ...c, index: i + 1 }));
}

export function splitCueAtChar(cue, charPos) {
  const text = cue.text;
  const n = text.length;
  const pos = Math.max(1, Math.min(charPos, n - 1));
  const ratio = pos / n;
  const tMid = cue.start + (cue.end - cue.start) * ratio;
  const a = {
    index: cue.index, start: cue.start, end: tMid,
    text: text.slice(0, pos).trim(),
    translations: { ...(cue.translations || {}) }, edited: true,
  };
  const b = {
    index: cue.index + 1, start: tMid, end: cue.end,
    text: text.slice(pos).trim(),
    translations: {}, edited: true,
  };
  return [a, b];
}

export function mergeCues(a, b) {
  const langs = new Set([
    ...Object.keys(a.translations || {}),
    ...Object.keys(b.translations || {}),
  ]);
  const translations = {};
  for (const lang of langs) {
    const ta = (a.translations || {})[lang] || "";
    const tb = (b.translations || {})[lang] || "";
    translations[lang] = `${ta} ${tb}`.replace(/\s+/g, " ").trim();
  }
  return {
    index: a.index, start: a.start, end: b.end,
    text: `${a.text} ${b.text}`.replace(/\n/g, " ").replace(/\s+/g, " ").trim(),
    translations, edited: true,
  };
}
