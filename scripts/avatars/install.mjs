import { mkdir, readFile, writeFile, copyFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { createHash } from "node:crypto";
import { root, modelHome } from "../models/files.mjs";
import { acquire, stop } from "../models/acquire.mjs";

// Downloads the pinned open-licence avatar sources, verifies them, and converts each with
// Blender into apps/web/public/avatars (not committed; config/avatar-register.json pins it).
const register = JSON.parse(await readFile(path.join(root, "config/avatar-register.json"), "utf8"));
const blender = process.env.BLENDER || "/Applications/Blender.app/Contents/MacOS/Blender";
const sourceDir = path.join(modelHome, "avatars", register.source.commit);
const outDir = path.join(root, "apps/web/public/avatars");
const artifact = (file) => ({ ...file, source: register.source.raw_base + file.path });

try {
  const version = spawnSync(blender, ["--version"], { encoding: "utf8" });
  if (version.status !== 0) throw new Error(`Blender not found at ${blender}; install Blender ${register.converter.blender_version} or set BLENDER`);
  if (!version.stdout.includes(`Blender ${register.converter.blender_version}`))
    throw new Error(`Blender ${register.converter.blender_version} is required; found ${version.stdout.split("\n")[0]}`);
  await mkdir(outDir, { recursive: true });
  await acquire(path.join(sourceDir, register.source.licence_file.path), artifact(register.source.licence_file));
  await copyFile(path.join(sourceDir, register.source.licence_file.path), path.join(outDir, "LICENSE-ROCKETBOX.md"));
  const manifest = [];
  for (const avatar of register.avatars) {
    for (const file of avatar.files) await acquire(path.join(sourceDir, file.path), artifact(file));
    const fbx = path.join(sourceDir, avatar.files.find((f) => f.path.endsWith(".fbx")).path);
    const out = path.join(outDir, `${avatar.id}.glb`);
    const report = path.join(sourceDir, `${avatar.id}.report.json`);
    // Textures sit in a sibling folder; Blender's image search finds them from the FBX.
    const result = spawnSync(blender, ["--background", "--factory-startup", "--python",
      path.join(root, register.converter.script), "--", fbx, path.join(path.dirname(fbx), "..", "Textures"), out,
      String(register.converter.texture_size), report],
      { encoding: "utf8", cwd: path.dirname(fbx) });
    if (result.status !== 0) { console.error(result.stdout.slice(-2000), result.stderr.slice(-2000)); throw new Error(`Conversion failed: ${avatar.id}`); }
    const details = JSON.parse(await readFile(report, "utf8"));
    if (details.shape_keys.length !== 67) throw new Error(`${avatar.id}: expected 67 shape keys, found ${details.shape_keys.length}`);
    if (details.metallic.some((m) => m !== 0)) throw new Error(`${avatar.id}: materials must not be metallic`);
    if (details.images.length < 4) throw new Error(`${avatar.id}: expected the character's textures, found ${details.images.join(", ") || "none"}`);
    const sha256 = createHash("sha256").update(await readFile(out)).digest("hex");
    manifest.push({ id: avatar.id, sex: avatar.sex, file: `${avatar.id}.glb`, bytes: details.bytes, sha256, shape_keys: details.shape_keys.length });
    console.log(`Converted ${avatar.id}: ${(details.bytes / 1e6).toFixed(1)} MB, ${details.shape_keys.length} shape keys`);
  }
  await writeFile(path.join(outDir, "manifest.json"), JSON.stringify({ source: register.source.commit, avatars: manifest }, null, 2) + "\n");
} catch (error) {
  stop();
  console.error(error.message);
  process.exitCode = 1;
}
