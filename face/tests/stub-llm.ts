// face/tests/stub-llm.ts
/** A scripted model route for the smoke tests: no key, no network. Only
 * `stream()` is abstract on `LlmAdapter`; the catalog methods are answered so
 * `session.models`/`selectModel` and `resolveCallConfig` accept the route.
 * The script decides per request (it sees the session id and the messages);
 * a thrown script is dsh's "iteration failure" → `turn/end {kind:'error'}`. */
// dsh 0.2.0 renamed the tool-call brand `CallId` -> `ToolCallId` (NEW
// packages/llm/llm/src/brand.ts:31-39, commit a789637db6); `StreamChunk`'s
// `tool-call-delta.id` is typed with it (types.ts:452-465). Everything else
// used here is unchanged against the installed dsh-llm .d.ts: only `stream` is
// abstract (index.ts:208-287), `LlmModelInfo`/`LlmResolvedModelInfo` gained
// optional fields only. Loop-built requests carry the system prompt as the
// leading `role:'system'` message, not `options.system` (types.ts:511-527) -
// scripts that inspect the prompt must read `options.messages`.
import { LlmAdapter, ToolCallId, type GenerateOptions, type LlmModelInfo, type LlmResolvedModelInfo, type StreamChunk } from "@deepseek-ai/dsh-llm";

export type StubReply =
  | { kind: "text"; text: string }
  | { kind: "tool"; name: string; args: unknown }
  | { kind: "error"; message: string };

let calls = 0;

export class StubAdapter extends LlmAdapter {
  constructor(private readonly script: (options: GenerateOptions) => StubReply) { super(); }
  override providerInfo(provider: string) { return { id: provider, name: "Stub" }; }
  override listModels(provider: string): Promise<readonly LlmModelInfo[]> {
    return Promise.resolve([{ provider, id: "echo", name: "echo", inputModalities: ["text"] }]);
  }
  override resolveModel(provider: string, model: string): Promise<LlmResolvedModelInfo> {
    return Promise.resolve({ provider, id: model, name: model, inputModalities: ["text"], context: { contextWindow: 128_000 } });
  }
  override async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const reply = this.script(options);
    if (reply.kind === "error") throw new Error(reply.message);
    if (reply.kind === "text") {
      yield { type: "block-start", index: 0, blockType: "text" };
      yield { type: "text-delta", index: 0, text: reply.text };
      yield { type: "block-end", index: 0, block: { type: "text", text: reply.text } };
      yield { type: "usage", usage: { inputTokens: 1, outputTokens: 1 } };
      yield { type: "finish", reason: { kind: "stop" } };
      return;
    }
    const id = ToolCallId(`stub-call-${++calls}`);
    const args = JSON.stringify(reply.args);
    yield { type: "block-start", index: 0, blockType: "tool-call" };
    yield { type: "tool-call-delta", index: 0, id, name: reply.name, argumentsDelta: args };
    yield { type: "block-end", index: 0, block: { type: "tool-call", id, name: reply.name, arguments: args } };
    yield { type: "finish", reason: { kind: "tool-calls" } };
  }
}
