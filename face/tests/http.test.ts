import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import type { IncomingMessage } from "node:http";
import { FORBIDDEN, HttpError, readBody } from "../src/http.ts";

function bodyReq(text: string): IncomingMessage {
  return Readable.from([Buffer.from(text)]) as unknown as IncomingMessage;
}

test("readBody returns the whole body under the limit", async () => {
  assert.equal(await readBody(bodyReq('{"name":"x"}')), '{"name":"x"}');
});

test("readBody refuses a body over the limit with a 413 HttpError", async () => {
  await assert.rejects(
    readBody(bodyReq("x".repeat(5000))),
    (err: HttpError) => err instanceof HttpError && err.status === 413,
  );
});

test("readBody honours a caller's own limit", async () => {
  assert.equal(await readBody(bodyReq("abc"), 3), "abc");
  await assert.rejects(readBody(bodyReq("abcd"), 3), (err: HttpError) => err.status === 413);
});

test("FORBIDDEN is fixed text that echoes nothing", () => {
  assert.equal(FORBIDDEN, '{"ok":false,"error":"forbidden"}');
});
