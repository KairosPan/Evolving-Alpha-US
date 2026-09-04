/** The HTTP primitives every `/data/*` route family shares: one error shape,
 * one body reader, one refusal body.
 *
 * These lived in strategies.ts because that was the first route family; they
 * were never about strategies. sessions.ts, panels.ts and channels.ts all
 * throw the same error and read bodies the same way, so the home is here.
 * @module
 */
import type { IncomingMessage } from "node:http";

/** Body of a refused (non-loopback) request. Fixed text: a refusal never
 * echoes anything the caller sent, including the Host it forged. */
export const FORBIDDEN = '{"ok":false,"error":"forbidden"}';

/** Most bytes a POST body may carry by default; ids and names need far
 * fewer, and a route carrying prose (an agent prompt) names its own. */
const BODY_LIMIT = 4096;

/** An http status plus a fixed, operator-facing reason. Route handlers catch
 * it and answer with `{status, message}`; anything else becomes a generic
 * 500 so a filesystem error never reaches a response body. */
export class HttpError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

/** Collect a request body up to `limit` bytes (default {@link BODY_LIMIT});
 * longer is refused with a 413 before the bytes are kept. */
export async function readBody(req: IncomingMessage, limit: number = BODY_LIMIT): Promise<string> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buf.length;
    if (size > limit) throw new HttpError(413, "body too large");
    chunks.push(buf);
  }
  return Buffer.concat(chunks).toString("utf8");
}
