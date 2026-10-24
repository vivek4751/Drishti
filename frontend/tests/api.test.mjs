import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";
import ts from "typescript";
const source = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8")
  .replace("import.meta.env.VITE_API_BASE", JSON.stringify("http://127.0.0.1:8000"));
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
const { queuedFetch } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("submission polls until the worker succeeds", async () => {
  const responses = [Response.json({ job_id: "a".repeat(32) }, { status: 202 }),
    Response.json({ status: "STARTED" }), Response.json({ status: "SUCCESS", result: { verdict: "REAL" } })];
  const calls = [];
  const originalFetch = globalThis.fetch;
  const originalTimer = globalThis.setTimeout;
  globalThis.setTimeout = (fn) => { fn(); return 0; };
  globalThis.fetch = async (...args) => { calls.push(args); return responses.shift(); };
  try {
    const response = await queuedFetch("http://127.0.0.1:8000/analyze/image", { method: "POST" });
    assert.deepEqual(await response.json(), { verdict: "REAL" });
    assert.equal(calls.length, 3);
    assert.equal(calls[1][0], "http://127.0.0.1:8000/jobs/" + "a".repeat(32));
  } finally { globalThis.fetch = originalFetch; globalThis.setTimeout = originalTimer; }
});

test("worker errors are shown instead of rendered as detections", async () => {
  const originalFetch = globalThis.fetch;
  const originalTimer = globalThis.setTimeout;
  const responses = [Response.json({ job_id: "b".repeat(32) }, { status: 202 }),
    Response.json({ status: "FAILURE", error: "Model unavailable" })];
  globalThis.setTimeout = (fn) => { fn(); return 0; };
  globalThis.fetch = async () => responses.shift();
  try {
    await assert.rejects(queuedFetch("/analyze/video", { method: "POST" }), /Model unavailable/);
  } finally { globalThis.fetch = originalFetch; globalThis.setTimeout = originalTimer; }
});

test("HTTP validation errors pass through without polling", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ detail: "Too large" }, { status: 413 });
  try { assert.equal((await queuedFetch("/analyze/image", {})).status, 413); }
  finally { globalThis.fetch = originalFetch; }
});

test("invalid job IDs cannot redirect polling to another URL", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ job_id: "https://other.example" }, { status: 202 });
  try { await assert.rejects(queuedFetch("/analyze/image", {}), /Invalid job/); }
  finally { globalThis.fetch = originalFetch; }
});
