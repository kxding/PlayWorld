import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const clientDir = path.join(root, "dist", "client");
const pagesDir = path.join(root, "pages");
const galleryDir = path.join(pagesDir, "gallery");
const basePath = "/PlayWorld/gallery/";

const assetDirectories = ["assets", "demos", "figures", "hero-mosaic", "posters"];
const rootAssets = ["favicon.svg", "file.svg", "globe.svg", "og.jpg", "window.svg"];

function rewriteBasePaths(source) {
  let output = source;
  for (const directory of assetDirectories) {
    output = output.replaceAll(`/${directory}/`, `${basePath}${directory}/`);
  }
  for (const asset of rootAssets) {
    output = output.replaceAll(`/${asset}`, `${basePath}${asset}`);
  }
  return output;
}

async function rewriteBuiltAssets(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await rewriteBuiltAssets(target);
    } else if (/\.(?:html|css|js)$/.test(entry.name)) {
      const source = await readFile(target, "utf8");
      await writeFile(target, rewriteBasePaths(source));
    }
  }
}

await rm(pagesDir, { recursive: true, force: true });
await mkdir(galleryDir, { recursive: true });
await cp(clientDir, galleryDir, { recursive: true });

const workerUrl = pathToFileURL(path.join(root, "dist", "server", "index.js"));
workerUrl.searchParams.set("gallery-export", Date.now().toString());
const { default: worker } = await import(workerUrl.href);
const response = await worker.fetch(
  new Request("https://kxding.github.io/", { headers: { accept: "text/html" } }),
  { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
  { waitUntil() {}, passThroughOnException() {} },
);

if (!response.ok) throw new Error(`Gallery render failed with status ${response.status}`);
await writeFile(path.join(galleryDir, "index.html"), rewriteBasePaths(await response.text()));
await rewriteBuiltAssets(galleryDir);
await writeFile(path.join(pagesDir, ".nojekyll"), "");
await writeFile(
  path.join(pagesDir, "index.html"),
  '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=./gallery/"><title>PlayWorld</title><a href="./gallery/">Open PlayWorld Gallery</a>',
);

console.log(`Exported PlayWorld Gallery to ${galleryDir}`);
