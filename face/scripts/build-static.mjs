import { copyFile, lstat, mkdir, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const faceDir = fileURLToPath(new URL("../", import.meta.url));
const landingDir = join(faceDir, "landing");
const outputDir = join(faceDir, "dist");
const publicFiles = [
  "index.html",
  "styles.css",
  "main.js",
  "favicon.svg",
  "social-card.svg",
  "social-card.png",
  "demo-research.webp",
  "demo-market.webp",
  "demo-account.webp",
];

// Publish only these landing-page files. The local workbench and its runtime
// data never enter the public output; symlinks are not accepted as sources.
if (!(await lstat(landingDir)).isDirectory()) {
  throw new Error("The landing source must be a directory, not a symlink");
}
await Promise.all(
  publicFiles.map(async (file) => {
    if (!(await lstat(join(landingDir, file))).isFile()) {
      throw new Error(`The landing asset must be a regular file: ${file}`);
    }
  }),
);

// Check the complete allowlist before replacing the previous output.
await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });
await Promise.all(
  publicFiles.map((file) =>
    copyFile(join(landingDir, file), join(outputDir, file)),
  ),
);
console.log(
  `Built the product landing page (${publicFiles.length} files) in ${outputDir}`,
);
