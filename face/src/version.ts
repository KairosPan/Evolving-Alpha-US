/** The dsh family version this face is built against. Upgrade = bump here +
 * package.json together, then run the README upgrade drill (spec section 4). */
export const DSH_PIN = "0.1.1-rc.2";

/** cordis is versioned on its own 4.x track, not with the dsh family — the dsh
 * packages peer-depend on it at `^4.0.1`, and the cordis-plugin-* family that
 * dsh-app-boot pulls in currently peers `^4.0.2`. Bump this + package.json
 * together, and re-run the upgrade drill. */
export const CORDIS_PIN = "4.0.2";
