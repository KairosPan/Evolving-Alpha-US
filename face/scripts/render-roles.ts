/** Regenerates `bots/gravit/agent.cordis.yml`, the mirror of Gravit's composition, from
 * `roles/` and `dsh/profile/cycle.md`: the one way that file is written (a hand edit fails
 * tests/roles.test.ts).
 *
 *     cd face && npm run render:roles
 *
 * Run it after any edit under `roles/` or to `dsh/profile/cycle.md`, then commit both.
 * Prints the path it wrote.
 */
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { COMPOSITION_FILE } from "../src/bot-presets.ts";
import { CYCLE_PATH, readCycle } from "../src/cycle.ts";
import { BOTS_ROOT, DEFAULT_PRESET } from "../src/overlay.ts";
import { ROLES_ROOT, readRoles, renderGravitComposition } from "../src/roles.ts";

const target = join(BOTS_ROOT, DEFAULT_PRESET, COMPOSITION_FILE);
writeFileSync(target, renderGravitComposition(readRoles(ROLES_ROOT), { cycle: readCycle(CYCLE_PATH) }));
console.log(target);
