import test from "node:test";
import assert from "node:assert/strict";
import { CORDIS_PIN, DSH_PIN } from "../src/version.ts";
import { createRequire } from "node:module";

test("every installed @deepseek-ai package matches the pin", () => {
  assert.equal(DSH_PIN, "0.1.1-rc.2");
  const require = createRequire(import.meta.url);
  for (const pkg of [
    "@deepseek-ai/dsh-app-boot", "@deepseek-ai/dsh-base",
    "@deepseek-ai/dsh-host-apiproxy", "@deepseek-ai/dsh-host-webserver",
    "@deepseek-ai/dsh-client-connection",
  ]) {
    const version = require(`${pkg}/package.json`).version as string;
    assert.equal(version, DSH_PIN, pkg);
  }
});

// cordis rides its own version track (4.x), not the dsh 0.1.1-rc.2 family — the
// dsh packages peer-depend on it at ^4.0.1. Pin it separately so an upgrade of
// either track is a deliberate edit here.
test("cordis matches its own pin", () => {
  assert.equal(CORDIS_PIN, "4.0.2");
  const require = createRequire(import.meta.url);
  const version = require("@deepseek-ai/cordis/package.json").version as string;
  assert.equal(version, CORDIS_PIN, "@deepseek-ai/cordis");
});
