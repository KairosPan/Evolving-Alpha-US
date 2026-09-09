import assert from "node:assert/strict";
import test from "node:test";
import { createAnswerTraces } from "../client/answer-traces.js";

/** Only the DOM operations the trace controller uses; moving a node detaches
 * it, and connectedness follows its ancestors as it does in the browser. */
class Element {
  children: Element[] = [];
  parent: Element | null = null;
  className = "";
  textContent = "";
  open = false;
  root = false;
  constructor(readonly tagName = "div") {}
  get childElementCount() { return this.children.length; }
  get isConnected(): boolean { return this.root || (this.parent?.isConnected ?? false); }
  classList = {
    add: (name: string) => { if (!this.hasClass(name)) this.className += ` ${name}`; },
    remove: (name: string) => { this.className = this.className.split(/\s+/).filter((c) => c !== name).join(" "); },
  };
  hasClass(name: string) { return this.className.split(/\s+/).includes(name); }
  setAttribute(name: string, _value: string) { if (name === "open") this.open = true; }
  append(...nodes: Element[]) {
    for (const node of nodes) { node.remove(); node.parent = this; this.children.push(node); }
  }
  before(node: Element) {
    const parent = this.parent;
    assert.ok(parent, "before() requires a parent");
    node.remove();
    parent.children.splice(parent.children.indexOf(this), 0, node);
    node.parent = parent;
  }
  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  querySelector(selector: string): Element | null {
    assert.ok(selector.startsWith("."));
    for (const child of this.children) {
      if (child.hasClass(selector.slice(1))) return child;
      const match = child.querySelector(selector);
      if (match) return match;
    }
    return null;
  }
}

function withDOM(run: (flow: Element, traces: ReturnType<typeof createAnswerTraces>) => void) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "document");
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { createElement: (tag: string) => new Element(tag) },
  });
  try {
    const flow = new Element();
    flow.root = true;
    run(flow, createAnswerTraces(() => flow));
  } finally {
    if (previous) Object.defineProperty(globalThis, "document", previous);
    else Reflect.deleteProperty(globalThis, "document");
  }
}

function answer(flow: Element) {
  const message = new Element();
  const bubble = new Element();
  bubble.className = "bubble";
  message.append(bubble);
  flow.append(message);
  return { message, bubble };
}

test("pending context and tool rows stay connected, then move into a closed answer disclosure", () => withDOM((flow, traces) => {
  const context = new Element("article"), tool = new Element("article");
  traces.add(context);
  traces.add(tool);
  assert.ok(context.isConnected && tool.isConnected);
  const details = flow.children[0];
  assert.equal(details.tagName, "details");
  assert.equal(details.querySelector(".trace-count")?.textContent, "2");
  const { message, bubble } = answer(flow);
  traces.attach(message);
  assert.deepEqual(flow.children, [message]);
  assert.equal(bubble.children.at(-1), details);
  assert.equal(details.open, false);
  assert.equal(details.hasClass("trace-pending"), false);
  assert.deepEqual(details.querySelector(".trace-content")?.children, [context, tool]);
  assert.ok(context.isConnected && tool.isConnected);
  // Result delivery still addresses the exact call node, including after attach.
  tool.textContent = "done";
  assert.equal(details.querySelector(".trace-content")?.children[1].textContent, "done");
}));

test("boundaries leave unanswered traces accessible without attaching them to the next answer", () => withDOM((flow, traces) => {
  const oldRow = new Element(), nextRow = new Element();
  traces.add(oldRow);
  const previousTrace = flow.children[0];
  traces.boundary();
  traces.add(nextRow);
  const { message, bubble } = answer(flow);
  traces.attach(message);
  assert.deepEqual(flow.children, [previousTrace, message]);
  assert.equal(previousTrace.querySelector(".trace-content")?.children[0], oldRow);
  assert.deepEqual(bubble.querySelector(".trace-content")?.children, [nextRow]);
  assert.ok(oldRow.isConnected);
}));

test("reset isolates the next session from previously pending traces", () => withDOM((flow, traces) => {
  const oldRow = new Element();
  traces.add(oldRow);
  traces.reset();
  for (const child of [...flow.children]) child.remove();
  const { message, bubble } = answer(flow);
  traces.attach(message);
  assert.equal(bubble.querySelector(".answer-trace"), null);
  const currentRow = new Element();
  traces.add(currentRow);
  traces.attach(message);
  assert.deepEqual(bubble.querySelector(".trace-content")?.children, [currentRow]);
  assert.equal(oldRow.isConnected, false);
}));

test("partial compaction preserves surviving rows when their answer is removed", () => withDOM((flow, traces) => {
  const surviving = new Element(), replaced = new Element();
  traces.add(surviving);
  traces.add(replaced);
  const { message } = answer(flow);
  traces.attach(message);
  const doomed = new Set([message, replaced]);
  traces.beforeRemove(doomed);
  for (const node of doomed) node.remove();
  traces.prune();
  assert.equal(flow.children.length, 1);
  const details = flow.children[0];
  assert.equal(details.hasClass("trace-pending"), true);
  assert.deepEqual(details.querySelector(".trace-content")?.children, [surviving]);
  assert.equal(details.querySelector(".trace-count")?.textContent, "1");
  assert.ok(surviving.isConnected);
  const next = answer(flow);
  traces.attach(next.message);
  assert.equal(next.bubble.querySelector(".answer-trace"), null);
}));

test("compaction prunes empty pending and attached disclosures without removing answers", () => withDOM((flow, traces) => {
  const first = new Element();
  traces.add(first);
  first.remove();
  traces.prune();
  assert.equal(flow.children.length, 0);
  const second = new Element();
  traces.add(second);
  const { message, bubble } = answer(flow);
  traces.attach(message);
  assert.ok(second.isConnected, "a new trace must not reuse a detached pending group");
  second.remove();
  traces.prune();
  assert.deepEqual(flow.children, [message]);
  assert.equal(bubble.querySelector(".answer-trace"), null);
}));
