// Build the pinned whisper.cpp server with Metal and download verified Whisper models.
// Usage: npm run speech:install [-- --models ggml-small.en.bin,ggml-base.en.bin]
import { copyFile, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { checksum } from "../models/files.mjs";
import { acquire, run, stop } from "../models/acquire.mjs";
import { installDirectory, installRecord, model, modelHome, modelPath, serverFile, speech } from "./files.mjs";

const flag = process.argv.indexOf("--models");
const requested = flag >= 0 ? process.argv[flag + 1].split(",") : [speech.default_model];

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("This runtime is for native Apple Silicon only.");
  const archive = path.join(modelHome, "downloads", speech.source.filename);
  await Promise.all([
    acquire(archive, speech.source),
    ...requested.map((name) => acquire(modelPath(name), model(name))),
  ]);
  const source = path.join(installDirectory, "src");
  const build = path.join(installDirectory, "build");
  await rm(installDirectory, { recursive: true, force: true });
  await mkdir(source, { recursive: true });
  await run("tar", ["-xzf", archive, "-C", source, "--strip-components", "1"]);
  // CMake comes from its pinned PyPI wheel via uv, so no Homebrew install is needed.
  const cmake = ["uvx", "--from", `cmake==${speech.build.cmake}`, "cmake"];
  console.log(`Building ${speech.build.target} ${speech.version} with Metal (about a minute)…`);
  await run(cmake[0], [...cmake.slice(1), "-S", source, "-B", build, ...speech.build.flags]);
  await run(cmake[0], [...cmake.slice(1), "--build", build, "--config", "Release", "--parallel", "8",
    "--target", speech.build.target]);
  await copyFile(path.join(build, "bin", speech.build.target), serverFile);
  await rm(source, { recursive: true, force: true });
  await rm(build, { recursive: true, force: true });
  await writeFile(installRecord, JSON.stringify({
    name: speech.name, version: speech.version, commit: speech.commit,
    source_sha256: speech.source.checksum_sha256, build: speech.build,
    binary_sha256: await checksum(serverFile), installed_at: new Date().toISOString(),
  }, null, 2) + "\n");
  console.log(`Verified speech installation: ${serverFile}`);
} catch (error) {
  stop();
  console.error(error.message);
  process.exitCode = 1;
}
