// Serve the voice-activity model and its runtime from this app (public/vad), not a CDN.
// Files come from the exact-pinned npm packages (lockfile integrity); a manifest records them.
import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const vad = path.dirname(require.resolve("@ricky0123/vad-web/package.json"));
// onnxruntime-web (a dependency of vad-web) does not export its package.json: walk up.
let ort = path.dirname(createRequire(path.join(vad, "package.json")).resolve("onnxruntime-web"));
while (!(await readFile(path.join(ort, "package.json"), "utf8").then((t) => JSON.parse(t).name === "onnxruntime-web", () => false))) ort = path.dirname(ort);
const out = path.join(import.meta.dirname, "..", "public", "vad");
const files = [
  [vad, "dist/vad.worklet.bundle.min.js"],
  [vad, "dist/silero_vad_v5.onnx"],
  [ort, "dist/ort-wasm-simd-threaded.mjs"],
  [ort, "dist/ort-wasm-simd-threaded.wasm"],
];
await mkdir(out, { recursive: true });
const manifest = [];
for (const [base, file] of files) {
  const target = path.join(out, path.basename(file));
  await copyFile(path.join(base, file), target);
  manifest.push({ file: path.basename(file), sha256: createHash("sha256").update(await readFile(target)).digest("hex") });
}
const version = async (dir) => JSON.parse(await readFile(path.join(dir, "package.json"), "utf8")).version;
await writeFile(path.join(out, "manifest.json"), JSON.stringify({
  "@ricky0123/vad-web": await version(vad), "onnxruntime-web": await version(ort),
  model: "Silero VAD v5 (MIT)", files: manifest,
}, null, 2) + "\n");
