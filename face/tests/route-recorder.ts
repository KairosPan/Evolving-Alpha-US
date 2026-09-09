// face/tests/route-recorder.ts
/** Drive registered routes offline: a `RouteRegistrar` that records what a
 * module registers, plus one `call` that plays a request through a route's
 * handler and hands back what the handler wrote. Same fakes the older route
 * tests build inline (`fakeRes` / `postReq` in bots.test.ts, channels.test.ts)
 * with the registrar folded in, so a route test needs one object. */
import type { IncomingMessage, ServerResponse } from "node:http";
import { Readable } from "node:stream";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";

export interface RouteCall {
  method?: string;
  /** The request body, JSON-encoded for you; sets `content-type: application/json`. */
  json?: unknown;
  /** A raw body, when the test wants junk or another content type. */
  body?: string;
  /** `Host`, defaulting to the face's own loopback address. */
  host?: string;
  headers?: Record<string, string>;
}

export interface RouteRecorder {
  register(route: WebRoute): void;
  /** The paths registered, in registration order. */
  paths(): string[];
  /** Play one request; returns `JSON.stringify({ status, body })`, the body parsed when it is JSON. */
  call(path: string, options?: RouteCall): Promise<string>;
}

export function recorder(): RouteRecorder {
  const routes: WebRoute[] = [];
  return {
    register(route: WebRoute): void { routes.push(route); },
    paths(): string[] { return routes.map((route) => route.path); },
    async call(path: string, options: RouteCall = {}): Promise<string> {
      const route = routes.find((r) => r.path === path);
      if (route === undefined) throw new Error(`no route is registered at ${path}`);
      const body = options.json === undefined ? options.body : JSON.stringify(options.json);
      const headers: Record<string, string> = {
        host: options.host ?? "127.0.0.1:3090",
        ...(options.json === undefined ? {} : { "content-type": "application/json" }),
        ...options.headers,
      };
      const method = options.method ?? "GET";
      const req = (body === undefined
        ? { headers, method }
        : Object.assign(Readable.from([Buffer.from(body)]), { headers, method })) as unknown as IncomingMessage;
      const out = { status: 0, body: "" };
      const res = {
        writeHead(status: number) { out.status = status; return res; },
        end(chunk?: string | Buffer) { out.body = String(chunk ?? ""); return res; },
      };
      await route.handler(req, res as unknown as ServerResponse);
      let parsed: unknown = out.body;
      try { parsed = JSON.parse(out.body); } catch { /* not JSON: hand back the bytes */ }
      return JSON.stringify({ status: out.status, body: parsed });
    },
  };
}
