/** Project-owned A-share MCP connection, below the operator's profile layer. */
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
