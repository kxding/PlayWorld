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
  assert.match(html, /<h1>PlayWorld<\/h1>/);
  assert.match(html, /hero-mosaic\/genie-gc004\.mp4/);
  assert.match(html, /hero-mosaic\/happyoyster-gc016\.mp4/);
  assert.equal((html.match(/hero-mosaic\//g) ?? []).length, 40);
  assert.doesNotMatch(html, /01 \/ THE QUESTION/);
  assert.match(html, /Model demos/);
  assert.match(html, /<strong>9\+<\/strong><span>Models<\/span>/);
  assert.match(html, /Geometry Consistency/);
  assert.match(html, /Interaction Fidelity/);
  assert.match(html, /Insight Evolution/);
  assert.match(html, /Out-of-sight Evolution/);
  assert.match(html, /Model ranking/);
  assert.match(html, /Ranking metric/);
  assert.match(html, /Overview of PlayWorld/);
  assert.match(html, /Comparison of world-model evaluation benchmarks/);
  assert.match(html, /<table class="benchmark-table">/);
  assert.doesNotMatch(html, /Selected paper figures/);
  assert.doesNotMatch(html, /table1-latest\.jpg/);
  assert.match(html, /VQA-based evaluation/);
  assert.match(html, /Basic video quality/);
  assert.match(html, /Memory consistency and action alignment/);
  assert.doesNotMatch(html, /TABLE 2|TABLE 3|Figure 1\.|Table 1\./);
  assert.match(html, new RegExp("/og\\.jpg"));
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/);
});
