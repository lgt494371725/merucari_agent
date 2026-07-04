// Pure dedup / cap logic for the recent-searches dropdown.
// Loaded as <script src=...> in the browser (exposes window.RecentKeywords)
// and via require() from the Node test runner.
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.RecentKeywords = factory();
  }
}(typeof self !== "undefined" ? self : this, function () {
  // Add `kw` to the front of `list`, deduping case-sensitively, capped at `max`.
  // Empty / whitespace-only keywords are ignored (returns list capped at max).
  function add(list, kw, max) {
    const arr = Array.isArray(list) ? list : [];
    const v = typeof kw === "string" ? kw.trim() : "";
    if (!v) return arr.slice(0, max);
    return [v, ...arr.filter(function (x) { return x !== v; })].slice(0, max);
  }

  // Remove all occurrences of `kw` from `list`.
  function remove(list, kw) {
    const arr = Array.isArray(list) ? list : [];
    return arr.filter(function (x) { return x !== kw; });
  }

  // Sanitize a value coming out of localStorage / JSON.parse: must be a
  // string array, capped at `max`.
  function sanitize(value, max) {
    if (!Array.isArray(value)) return [];
    return value.filter(function (x) { return typeof x === "string"; }).slice(0, max);
  }

  function appendToken(text, token) {
    const base = typeof text === "string" ? text.trim().replace(/\s+/g, " ") : "";
    const v = typeof token === "string" ? token.trim() : "";
    if (!v) return base;
    const parts = base ? base.split(/\s+/) : [];
    if (parts.indexOf(v) !== -1) return base;
    return parts.concat([v]).join(" ");
  }

  return { add: add, remove: remove, sanitize: sanitize, appendToken: appendToken };
}));
