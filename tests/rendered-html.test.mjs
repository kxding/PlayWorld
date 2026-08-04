import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("server-renders the PlayWorld project page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>PlayWorld/);
  assert.match(html, /Can a generated world/);
  assert.match(html, /One long-horizon case/);
  assert.match(html, /Geometry Consistency/);
  assert.match(html, /Interaction Fidelity/);
  assert.match(html, /Insight Evolution/);
  assert.match(html, /Out-of-sight Evolution/);
  assert.match(html, new RegExp("/og\\.jpg"));
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});
