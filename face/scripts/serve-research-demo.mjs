/** Isolated screenshot fixture using the real channel renderer and client CSS.
 * Run from any directory: node face/scripts/serve-research-demo.mjs
 * Open http://127.0.0.1:4182 at 1440 x 1080. Nothing contacts the live host.
 * All research, names, and records below are illustrative public samples.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const face = fileURLToPath(new URL("../", import.meta.url));
const client = join(face, "client");
const assets = new Map([
  ["/client/chat.css", ["chat.css", "text/css"]],
  ["/client/navigation.js", ["navigation.js", "text/javascript"]],
  ["/client/channels.js", ["channels.js", "text/javascript"]],
  ["/client/markdown.js", ["markdown.js", "text/javascript"]],
]);
const payload = {
  channel: {
    title: "Sentiment & trend persistence",
    dir: "SAMPLE RESEARCH CHANNEL · ILLUSTRATIVE CONTENT",
    sessionIds: [],
  },
  status: {
    status: "researching",
    one_line: "A research question, with its assumptions and limits in view.",
    next: "Compare the hypothesis with alternative explanations.",
    numbers: {
      "Research question": "01",
      Perspectives: "03",
      Decision: "Open",
    },
  },
  agents: ["codex"],
  allBins: ["codex"],
  bots: ["trend", "evidence", "counterview"],
  allBots: [
    { id: "trend", name: "Trend view" },
    { id: "evidence", name: "Evidence review" },
    { id: "counterview", name: "Counterview" },
  ],
  body: {
    thesis: {
      isTemplate: false,
      markdown:
        "### Research question\nCan changes in market sentiment help explain whether a trend persists?\n\n### What would change our mind?\nRetire the hypothesis if the relationship does not repeat out of sample.\n\n### Before testing\n- Define the observation window and comparison benchmark.\n- Check which information was available at each observation.\n- Keep competing explanations in the research record.",
    },
    latest: {
      file: "Sample evidence review · no performance claim",
      json: {
        Hypothesis: "Defined before testing",
        "Data review": "Check availability at the time",
        Validation: "Out-of-sample evaluation pending",
      },
    },
    backtests: [],
    journal: [
      {
        date: "Step 01",
        text: "Frame the question and record falsification criteria.",
      },
      {
        date: "Step 02",
        text: "Compare perspectives before drawing a conclusion.",
      },
    ],
    files: [{ name: "Research brief.md", bytes: 2048, mtime: "2026-09-01" }],
  },
  sessions: [
    {
      sessionId: "sample-session",
      title: "Hypothesis and test plan",
      archived: false,
    },
  ],
};

const moduleSource = `
import "/client/navigation.js";
import { renderChannelPage } from "/client/channels.js";
const inner = document.createElement("div");
inner.className = "detail-inner";
document.querySelector("#detail").replaceChildren(inner);
document.querySelector(".main").classList.add("detail-mode");
document.querySelector("#topbar-name").textContent = "Strategy / Research overview";
document.querySelector("#topbar-raw").textContent = "SAMPLE CONTENT";
document.querySelector(".side-brand").textContent = "GRAVIT";
document.querySelector(".side-foot").textContent = "prototype · staged demo";
document.querySelector("#conv-list").innerHTML = \`
<div class="conv-group"><span class="chev">▾</span><span>Sentiment &amp; trends</span><span class="conv-group-n">3</span></div>
<div class="conv active"><div class="conv-top"><span class="conv-name">Research overview</span></div><div class="conv-sub"><span class="chip">researching</span></div></div>
<div class="conv"><div class="conv-top"><span class="conv-name">Compare the perspectives</span></div><div class="conv-sub"><span class="chip">discussion</span></div></div>
<div class="conv"><div class="conv-top"><span class="conv-name">Evidence &amp; next steps</span></div></div>
<div class="conv-group"><span class="chev">▾</span><span>Industry cycles</span><span class="conv-group-n">2</span></div>
<div class="conv"><div class="conv-top"><span class="conv-name">Frame a new hypothesis</span></div></div>
<div class="conv"><div class="conv-top"><span class="conv-name">A review of the evidence</span></div></div>
<div class="conv-group"><span class="chev">▸</span><span>New research ideas</span><span class="conv-group-n">1</span></div>\`;
const noop = () => {};
renderChannelPage(inner, ${JSON.stringify(payload)}, {
  onRename: noop, onToggleAgent: noop, onToggleBot: noop,
  onNewRound: noop, onOpenSession: noop,
});
document.documentElement.dataset.demoReady = "true";
`;

createServer(async (request, response) => {
  if (request.method !== "GET") {
    response.writeHead(405).end();
    return;
  }
  const path = new URL(request.url, "http://127.0.0.1:4182").pathname;
  try {
    if (path === "/") {
      const html = (await readFile(join(client, "index.html"), "utf8"))
        .replace(
          "<title>KAIROS</title>",
          "<title>Gravit — Research screenshot fixture</title>",
        )
        .replace('src="/client/chat.js"', 'src="/demo-research.js"');
      response
        .writeHead(200, { "content-type": "text/html; charset=utf-8" })
        .end(html);
    } else if (path === "/demo-research.js") {
      response
        .writeHead(200, { "content-type": "text/javascript; charset=utf-8" })
        .end(moduleSource);
    } else if (path === "/favicon.ico") {
      response.writeHead(204).end();
    } else if (assets.has(path)) {
      const [name, type] = assets.get(path);
      response
        .writeHead(200, { "content-type": type })
        .end(await readFile(join(client, name)));
    } else response.writeHead(404).end("Not found");
  } catch {
    response.writeHead(500).end("Could not load screenshot fixture");
  }
}).listen(4182, "127.0.0.1", () => {
  console.log(
    "Research screenshot fixture: http://127.0.0.1:4182 (1440 x 1080)",
  );
});
