/** Project-owned A-share MCP connection, below the operator's profile layer
 * (boot.ts composes it after dsh-base and the face's policy defaults, before
 * the profile and home patches), so the operator can replace or disable it.
 *
 * What dsh 0.2.0-rc.2 changed for this row, none of it a config change
 * (`satisfies StdioConfig` still holds; the new keys `maxInstructionBytes` and
 * `reconnect` are optional: NEW packages/mcp/mcp-client/src/index.ts:52-77):
 * - the client moved to `@modelcontextprotocol/client` 2.0 with version
 *   negotiation, and stdio negotiation "starts a temporary probe process before
 *   the serving process" (NEW packages/mcp/mcp-client/README.md:28): the
 *   server is spawned twice per connect. That the FastMCP (`mcp<2`) server
 *   negotiates at all is a live-drill check (PLAN S10 step 7);
 * - a connected server's `instructions` now enter the system prompt as section
 *   `mcp:<serverName>` (NEW packages/mcp/mcp-client/src/server-context.ts:
 *   28-39), with no switch - akshare-mcp sets them, so Kairos's prompt (and
 *   every bot's: sections are not masked like tools) gains an `mcp:akshare`
 *   section; instructions over `maxInstructionBytes` (32 KiB default) now FAIL
 *   the connection. */
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { StdioConfig } from "@deepseek-ai/dsh-mcp-client";
import type { FacePatchList } from "./boot.ts";

export const AKSHARE_MCP_ROW_ID = "mcp-akshare";

/** The executable is installed separately; startup never downloads packages.
 * An unavailable server is logged by dsh and does not take down the chat host.
 * Profile/home patches can replace this config or disable the row. */
export function aksharePatches(
  command = process.env.FACE_AKSHARE_MCP_COMMAND || join(homedir(), ".local", "bin", "akshare-mcp"),
): FacePatchList {
  return [{
    insert: [{
      id: AKSHARE_MCP_ROW_ID,
      name: "@deepseek-ai/dsh-mcp-client",
      config: {
        transport: "stdio",
        serverName: "akshare",
        command,
        args: [],
        cwd: fileURLToPath(new URL("../../", import.meta.url)),
        env: { PYTHONUNBUFFERED: "1", AKSHARE_MCP_MAX_ROWS: "500" },
        toolCallTimeoutMs: 120_000,
        failOnStartupError: false,
      } satisfies StdioConfig,
    }],
  }];
}
