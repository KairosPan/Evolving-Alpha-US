import { copyFile, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const faceDir = fileURLToPath(new URL("../", import.meta.url));
const clientDir = join(faceDir, "client");
const outputDir = join(faceDir, "dist");
const allowedExtensions = new Set([".html", ".css", ".js"]);
const pages = ["index.html", "market.html", "account.html"];
const notice = "前端已上线，后端尚未连接。聊天、行情和账户数据暂不可用。";
const noticeStyle = `<style>
.deployment-notice { flex: none; margin: 16px 20px; padding: 12px 16px; border: 1px solid #d8cba9; border-radius: 8px; background: #fff8e8; color: #57431d; font: 14px/1.6 system-ui, sans-serif; }
</style>`;

function hostedHtml(html) {
  if (!html.includes("</head>") || !/<main\b/.test(html)) {
    throw new Error("Each hosted page must have a head and main landmark");
  }
  return html
    .replace("</head>", `${noticeStyle}\n</head>`)
    .replace(/(<main\b[^>]*>)/, `$1\n<aside class="deployment-notice" role="status" lang="zh-CN">${notice}</aside>`)
    .replace("live · loopback only", "frontend · backend disconnected");
}

// Copy browser assets only. Symlinks, server code, runtime files and other
// extensions never enter the public output, even if added beside the client.
async function copyClient(directory) {
  let count = 0;
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const source = join(directory, entry.name);
    if (entry.isDirectory()) {
      count += await copyClient(source);
      continue;
    }
    if (!entry.isFile() || !allowedExtensions.has(extname(entry.name))) continue;
    const target = join(outputDir, "client", relative(clientDir, source));
    await mkdir(dirname(target), { recursive: true });
    if (extname(entry.name) === ".html") {
      await writeFile(target, hostedHtml(await readFile(source, "utf8")));
    } else {
      await copyFile(source, target);
    }
    count += 1;
  }
  return count;
}

// Validate required pages before replacing the previous output.
const pageContents = await Promise.all(pages.map(async (page) => [
  page, hostedHtml(await readFile(join(clientDir, page), "utf8")),
]));
await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });
const assetCount = await copyClient(clientDir);
for (const [page, html] of pageContents) await writeFile(join(outputDir, page), html);
console.log(`Built ${pages.length} pages and ${assetCount} browser assets in ${outputDir}`);
