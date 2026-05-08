// Tests for the recent-searches dedup/cap logic in static/recent_keywords.js.
//
// Run:
//   node --test tests/test_recent_keywords.mjs

import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const RK = require(path.join(here, "..", "static", "recent_keywords.js"));

test("add: pushes new keyword to the front", () => {
  assert.deepEqual(RK.add(["a", "b"], "c", 10), ["c", "a", "b"]);
});

test("add: dedupes — existing keyword is moved to front, no duplicates", () => {
  assert.deepEqual(RK.add(["a", "b", "c"], "b", 10), ["b", "a", "c"]);
  // and still no duplicates after a second push
  assert.deepEqual(RK.add(RK.add(["a", "b"], "a", 10), "a", 10), ["a", "b"]);
});

test("add: caps at max — oldest entries fall off", () => {
  const list = ["a", "b", "c"];
  assert.deepEqual(RK.add(list, "d", 3), ["d", "a", "b"]);
  assert.deepEqual(RK.add(list, "d", 2), ["d", "a"]);
});

test("add: trims whitespace around the keyword", () => {
  assert.deepEqual(RK.add(["a"], "  hello  ", 10), ["hello", "a"]);
  // the trimmed form deduplicates against an existing equal entry
  assert.deepEqual(RK.add(["hello", "a"], "  hello ", 10), ["hello", "a"]);
});

test("add: ignores empty/whitespace-only keywords (still caps existing list)", () => {
  assert.deepEqual(RK.add(["a", "b", "c"], "", 10), ["a", "b", "c"]);
  assert.deepEqual(RK.add(["a", "b", "c"], "   ", 10), ["a", "b", "c"]);
  assert.deepEqual(RK.add(["a", "b", "c"], "", 2), ["a", "b"]);
});

test("add: handles non-string / null keyword gracefully", () => {
  assert.deepEqual(RK.add(["a"], null, 10), ["a"]);
  assert.deepEqual(RK.add(["a"], undefined, 10), ["a"]);
  assert.deepEqual(RK.add(["a"], 42, 10), ["a"]);
});

test("add: handles a non-array list gracefully", () => {
  assert.deepEqual(RK.add(null, "a", 10), ["a"]);
  assert.deepEqual(RK.add(undefined, "a", 10), ["a"]);
});

test("add: case-sensitive dedup ('Nike' and 'nike' are distinct)", () => {
  assert.deepEqual(RK.add(["Nike"], "nike", 10), ["nike", "Nike"]);
});

test("remove: removes a single matching entry", () => {
  assert.deepEqual(RK.remove(["a", "b", "c"], "b"), ["a", "c"]);
});

test("remove: no-op when keyword is absent", () => {
  assert.deepEqual(RK.remove(["a", "b"], "z"), ["a", "b"]);
});

test("remove: handles non-array list", () => {
  assert.deepEqual(RK.remove(null, "a"), []);
});

test("sanitize: drops non-strings and caps", () => {
  assert.deepEqual(RK.sanitize(["a", 1, null, "b", { x: 1 }, "c"], 10), ["a", "b", "c"]);
  assert.deepEqual(RK.sanitize(["a", "b", "c", "d"], 2), ["a", "b"]);
});

test("sanitize: returns [] for non-array input", () => {
  assert.deepEqual(RK.sanitize(null, 10), []);
  assert.deepEqual(RK.sanitize("nope", 10), []);
  assert.deepEqual(RK.sanitize(42, 10), []);
});
