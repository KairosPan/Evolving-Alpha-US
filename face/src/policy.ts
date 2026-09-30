/** The face's policy layer: the 0.1.1-rc.2 product defaults that dsh-base
 * 0.2.0-rc.2 changed, restored in ONE reviewable place (PLAN §2, S4).
 *
 * Everything here changes what Kairos can do or what leaves the machine, so
 * every entry is a DECISION the operator owns (PLAN §6), named by its id. The
 * default is always "keep 0.1.1's behaviour"; following upstream instead is a
 * one-row operator patch, not a code change.
 *
 * WHERE IT COMPOSES (boot.ts `composeFace`): directly ABOVE the bundle layer
 * and BELOW everything the operator writes — AKShare, the profile's
 * `cordis.patch.yml`, the home layer. So an operator row with the same id wins
 * (the last write per row wins: NEW packages/bundle/base/cordis.patch.yml:1-4),
 * which is the opposite of the face's overlay rows, and on purpose: these are
 * defaults, not the face's contract.
 *
 * TWO PATCH RULES this file stands on (NEW vendor/include/src/index.ts:
 * 104-125): a non-insert patch overwrites ONLY the keys it names, so
 * `{ id, disabled }` keeps the row's config; but a named `config` REPLACES the
 * whole config, so a row whose config is patched is restated completely here
 * (`tool-web`, `web`). And a patch aimed at a row that is not there does
 * nothing, silently — hence every id patch is guarded on the row being in the
 * bundle composition, the absence is reported rather than swallowed, and
 * tests/policy.test.ts pins every id against the installed dsh-base.
 * @module
 */
import type { FacePatchList } from "./boot.ts";

/** One id-targeted restoration: which decision it implements, and the patch. */
export interface PolicyIdPatch {
  /** The PLAN §6 decision id and a short name, e.g. `D4 session-log upload`. */
  readonly decision: string;
  readonly patch: {
    readonly id: string;
    readonly disabled?: boolean;
    readonly config?: Readonly<Record<string, unknown>>;
  };
}

/** One row the face inserts because dsh-base stopped mounting it. */
export interface PolicyInsert {
  readonly decision: string;
  readonly row: { readonly id: string; readonly name: string };
}

/** The id-targeted restorations, in composition order. Each comment cites the
 * NEW dsh-base row it targets and the upstream change it undoes. */
export const POLICY_ID_PATCHES: readonly PolicyIdPatch[] = [
  /* D3. Upstream flipped the row's default mode from DISABLED to FEEDBACK_ONLY:
   * after a `/feedback` (dsh-base mounts `command-feedback`, base :310) it
   * uploads a session-log prefix to dsh-otel-collector.deepseeksvc.com with the
   * home's `.anonymous-user-id` (base :188-212; commit 106e5ce0bc; OLD base
   * :148-151 had `'DISABLED'`). Nothing hard-injects its service, so the row
   * can go. `DSH_TELEMETRY_DISABLED` still works on top (boot.ts). */
  { decision: "D3 telemetry", patch: { id: "session-telemetry-otel", disabled: true } },
  /* D4. New in dsh-base: owns the `dsh_session_log` request field and sends up
   * to `maxBytes` (8 MiB) of Session events on every official DeepSeek request
   * (base :43-44; NEW packages/session/session-log-deepseek/src/index.ts:34-53,
   * 182-223). New egress relative to 0.1.1. A function plugin: no service. */
  { decision: "D4 session-log upload", patch: { id: "session-log-deepseek", disabled: true } },
  /* D5. New in dsh-base: sends the active plugin-package list on every
   * DeepSeek request (base :77-78; NEW packages/llm/
   * plugin-package-inventory-deepseek/src/index.ts:27-39, 188-193). A function
   * plugin: no service. */
  { decision: "D5 package inventory", patch: { id: "plugin-package-inventory-deepseek", disabled: true } },
  /* D6, three rows. Upstream enabled `web_fetch` by default (commit
   * 0a0f9e59ff): `tool-web.fetch: true` plus a new `web-fetch-http` provider
   * and `web.fetchProvider: http` (base :472-490). 0.1.1 shipped fetch OFF
   * (OLD base :404-418). `tool-web` registers `web_fetch` iff `fetch` is set
   * (NEW packages/web/tool-web/src/index.ts:83-95). Both configs are restated
   * WHOLE (a named config replaces the row's), with 0.1.1's exact values; with
   * `fetchProvider` omitted, `web` falls back to `$DSH_WEB_FETCH_PROVIDER` (NEW
   * packages/web/web/src/index.ts:90-94), and with `web-fetch-http` disabled no
   * fetch provider exists for it to select anyway. */
  { decision: "D6 web_fetch", patch: { id: "tool-web", config: { fetch: false, searchTimeoutMs: 60000 } } },
  { decision: "D6 web_fetch", patch: { id: "web", config: { searchProvider: "deepseek-official" } } },
  { decision: "D6 web_fetch", patch: { id: "web-fetch-http", disabled: true } },
  /* D7. New in dsh-base (commit e08468954a; base :492-493): three global
   * model-facing tools (`list_mcp_resources`, `list_mcp_resource_templates`,
   * `read_mcp_resource`, NEW packages/mcp/mcp-resources/src/tools.ts:31-64)
   * plus a prompt section, once any MCP server registers. mcp-client
   * hard-injects only `tools` (NEW packages/mcp/mcp-client/src/index.ts:34)
   * and reaches `mcpResources` through an optional `ctx.inject`
   * (server-context.ts:29-31), so disabling it strands nothing. (The
   * `mcp:<server>` instructions section beside it has no switch; it stays.) */
  { decision: "D7 MCP resource tools", patch: { id: "mcp-resources", disabled: true } },
  /* D9, half one. dsh-base now ships `tool-ralph` DISABLED (base :440-452; its
   * own comment names this exact overlay row as the way back). It was enabled
   * at 0.1.1 (OLD base :378-382). `disabled: false` alone: the row keeps its
   * base config. */
  { decision: "D9 ralph", patch: { id: "tool-ralph", disabled: false } },
];

/** Rows dsh-base no longer mounts at all, inserted when (and only when) the
 * bundle composition lacks them — a second same-id insert would silently
 * REPLACE base's row (NEW vendor/include/src/index.ts:93-100). */
export const POLICY_INSERTS: readonly PolicyInsert[] = [
  /* D9, half two. Upstream removed the row from dsh-base (commit 36a4665144,
   * "overlapping file editing interfaces"); the package is still published
   * and pinned in package.json. 0.1.1 mounted it with `maxOutputChars: 16000`
   * (OLD base :384-387), which is now the schema default (NEW packages/fs/
   * tool-str-replace-editor/src/index.ts:514-515), so the insert is
   * configless. Its injects (`tools`, `fs`) are dsh-base rows. */
  { decision: "D9 str_replace_editor", row: { id: "tool-str-replace-editor", name: "@deepseek-ai/dsh-tool-str-replace-editor" } },
];

/**
 * The policy layer for one composition.
 * @param baseRows - the row ids the BUNDLE layer composes to (boot.ts:
 * `composedRowIds([bundlePatches])`) — what these patches are allowed to target.
 * @param onMissing - told, one line per restoration, when its target row is not
 * in the bundle composition. That is never expected at the pinned dsh-base
 * (tests/policy.test.ts), so it means the base moved under a pin bump: a RENAMED
 * row would otherwise carry its new default past this layer without a word.
 * @returns fresh patch objects, safe to compose and to mutate: every id patch
 * whose row exists, then one insert patch of the missing rows (omitted when
 * none is missing).
 */
export function facePolicyPatches(
  baseRows: ReadonlySet<string>,
  onMissing: (line: string) => void = () => {},
): FacePatchList {
  const out: FacePatchList = [];
  for (const { decision, patch } of POLICY_ID_PATCHES) {
    if (baseRows.has(patch.id)) out.push(structuredClone(patch) as FacePatchList[number]);
    else onMissing(`policy ${decision}: dsh-base composes no "${patch.id}" row, so there is nothing to restore - renamed upstream?`);
  }
  const inserts = POLICY_INSERTS.filter(({ row }) => !baseRows.has(row.id)).map(({ row }) => ({ ...row }));
  if (inserts.length > 0) out.push({ insert: inserts });
  return out;
}
