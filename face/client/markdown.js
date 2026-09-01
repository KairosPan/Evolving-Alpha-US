/** Markdown for Kairos bubbles, DOM-built.
 *
 * Kairos answers in markdown — headings, bold tickers, GFM tables — and a
 * plain-text bubble shows the asterisks and pipes literally. This renders the
 * subset Kairos actually writes, with the same discipline as the rest of the
 * client: every string lands via `textContent`, no `innerHTML` path at all, so
 * nothing in the text can smuggle markup. Anything outside the subset falls
 * through as literal text inside a paragraph — degraded, never dropped.
 *
 * Inline: `**bold**`, `` `code` ``, `[label](http…)`. Blocks: `#`–`####`
 * headings, `-`/`*`/`1.` lists (nested by two-space indent), GFM tables
 * (numeric columns right-aligned; signed percent/number cells colored with the
 * sign kept in the text), fenced code, `>` quotes, `---` rules, paragraphs.
 * @module
 */

/** @param {string} tag @param {string|null} [cls] @param {string} [text] */
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

const INLINE = /\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g;

/** Append `text` to `target` with inline markdown resolved. */
function inline(target, text) {
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) target.append(text.slice(last, m.index));
    if (m[1] !== undefined) target.append(el("strong", null, m[1]));
    else if (m[2] !== undefined) target.append(el("code", "md-code", m[2]));
    else {
      const a = el("a", null, m[3]);
      a.href = m[4];
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      target.append(a);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) target.append(text.slice(last));
}

/** A table cell's comparable text: inline markers stripped, trimmed. */
const cellText = (raw) => raw.replaceAll("**", "").replaceAll("`", "").trim();
const NUMERIC = /^[+\-−]?\$?[\d,.]+%?$/;

/** Split one `| a | b |` line into trimmed cell strings. */
function splitRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

/**
 * @param {string} text - the message's markdown.
 * @returns {{node: HTMLElement, doc: boolean}} the rendered tree, and whether
 *   it carries document structure (headings/tables/fences) — the caller may
 *   widen the bubble for a document but not for a chat-sized reply.
 */
export function renderMarkdown(text) {
  const root = el("div", "md");
  const lines = text.split("\n");
  let doc = false;
  let i = 0;

  /** flush a run of plain lines as one paragraph */
  let para = [];
  const flushPara = () => {
    if (!para.length) return;
    const p = el("p");
    para.forEach((line, k) => {
      if (k > 0) p.append("\n");
      inline(p, line);
    });
    root.append(p);
    para = [];
  };

  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {
      flushPara();
      const buf = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) { buf.push(lines[i]); i += 1; }
      i += 1; // the closing fence (or EOF)
      root.append(el("pre", "md-fence", buf.join("\n")));
      doc = true;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushPara();
      const h = el("div", `md-h md-h${heading[1].length}`);
      inline(h, heading[2].trim());
      root.append(h);
      doc = true;
      i += 1;
      continue;
    }

    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushPara();
      root.append(el("hr", "md-hr"));
      i += 1;
      continue;
    }

    // GFM table: a pipe row whose NEXT line is the |---|:---| separator.
    if (line.trimStart().startsWith("|") && i + 1 < lines.length &&
      /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      flushPara();
      const header = splitRow(line);
      const body = [];
      i += 2;
      while (i < lines.length && lines[i].trimStart().startsWith("|")) {
        body.push(splitRow(lines[i]));
        i += 1;
      }
      const numeric = header.map((_, col) => {
        const cells = body.map((r) => cellText(r[col] ?? "")).filter((c) => c !== "");
        return cells.length > 0 && cells.filter((c) => NUMERIC.test(c)).length >= cells.length * 0.6;
      });
      const table = el("table", "viz-table");
      const thead = el("thead");
      const hr = el("tr");
      header.forEach((cell, col) => {
        const th = el("th", numeric[col] ? "num" : null);
        inline(th, cell);
        hr.append(th);
      });
      thead.append(hr);
      table.append(thead);
      const tbody = el("tbody");
      for (const row of body) {
        const tr = el("tr");
        header.forEach((_, col) => {
          const raw = row[col] ?? "";
          const bare = cellText(raw);
          const td = el("td", numeric[col] ? "num" : null);
          if (/^\+\$?[\d,.]+%?$/.test(bare)) td.classList.add("up");
          else if (/^[-−]\$?[\d,.]+%?$/.test(bare)) td.classList.add("down");
          inline(td, raw);
          tr.append(td);
        });
        tbody.append(tr);
      }
      table.append(tbody);
      const wrap = el("div", "md-tablewrap");
      wrap.append(table);
      root.append(wrap);
      doc = true;
      continue;
    }

    const item = /^(\s*)([-*]|\d+[.)])\s+(.*)$/.exec(line);
    if (item) {
      flushPara();
      /** @type {{list: HTMLElement, depth: number}[]} */
      const stack = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (!m) break;
        const depth = Math.min(Math.floor(m[1].length / 2), 3);
        const ordered = /\d/.test(m[2]);
        while (stack.length > 0 && stack[stack.length - 1].depth > depth) stack.pop();
        const top = stack[stack.length - 1];
        if (!top || top.depth < depth ||
          (top.depth === depth && (top.list.tagName === "OL") !== ordered && stack.length === 1)) {
          const list = el(ordered ? "ol" : "ul", "md-list");
          if (top && top.depth < depth) (top.list.lastElementChild ?? top.list).append(list);
          else root.append(list);
          stack.push({ list, depth });
        }
        const li = el("li");
        inline(li, m[3]);
        stack[stack.length - 1].list.append(li);
        i += 1;
      }
      continue;
    }

    if (/^>\s?/.test(line)) {
      flushPara();
      const quote = el("blockquote", "md-quote");
      let first = true;
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        if (!first) quote.append("\n");
        inline(quote, lines[i].replace(/^>\s?/, ""));
        first = false;
        i += 1;
      }
      root.append(quote);
      continue;
    }

    if (line.trim() === "") { flushPara(); i += 1; continue; }
    para.push(line);
    i += 1;
  }
  flushPara();
  return { node: root, doc };
}
