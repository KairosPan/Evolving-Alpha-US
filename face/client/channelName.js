/** Pure whitespace fold for a typed channel name: the tested half of the
 * create box.
 *
 * No DOM, no network, no state — the string the operator typed in, the
 * directory name that will be created out. Split out of chat.js for the same
 * reason grouping.js is: the decision has to be drillable without a browser.
 *
 * WHAT IT IS NOT. It is not a fence. `createChannel` (src/channels.ts) keeps
 * the only gate standing between the create route and `join()`, and its rule
 * is untouched: a fold that ever produced a `.`, a separator or a leading dash
 * would be REFUSED, not obeyed. This runs before the POST so the operator gets
 * the channel they meant instead of a 400 they have to retype their way out
 * of; if the browser skips it, the server still refuses. Fail-closed.
 *
 * WHY A SPACE FOLDS INSTEAD OF BEING ALLOWED THROUGH. The closed class
 * guarantees a channel path is exactly ONE shell word opening on an
 * alphanumeric. The face never builds a shell string — `spawn` gets an argv
 * array and a `cwd` option — but Kairos does, and `cd` is what it has to
 * compose: a channel session starts in `strategies/<name>` while AGENTS.md tells
 * it to work from the repo root. Two words after `cd` are zsh's two-argument
 * form — word 1 replaced by word 2 in $PWD — which usually errors but exits 0
 * in the WRONG directory when the substituted path exists. `python` and
 * `git add` at least mis-parse a spaced path loudly; this one is silent.
 * @module
 */

/** Every run of whitespace — with any dashes touching it — becomes a single
 * `-`; whitespace at either end is dropped rather than becoming an edge dash.
 * A LEADING dash is the one `NAME_RE` refuses; a trailing one it would take,
 * but the operator never typed it either, so it goes too. A dash run typed
 * with no whitespace in it is left alone. NFC first, so this agrees with
 * `createChannel`'s own fold and one word typed in two normalizations stays
 * one directory.
 *
 * `\s` is doing real work beyond U+0020 here: a Chinese IME emits U+3000, and
 * a paste can carry U+00A0 or a newline. Those are invisible in the box and
 * were refused with the same unhelpful 400. It reaches Unicode White_Space
 * plus U+FEFF and no further, though: the Cf zero-widths U+200B–U+200D are invisible WITHOUT
 * being whitespace, so they pass through the fold unchanged and go on earning
 * their 400 from the server. Widening this class is not the fix for those.
 * @param {string} raw the operator's exact keystrokes
 * @returns {string} the directory name the create route will be asked for
 */
export function foldChannelName(raw) {
  return raw
    .normalize("NFC")
    .replace(/^\s+|\s+$/gu, "")   // edge whitespace goes, it never becomes a dash
    .replace(/[\s-]*\s[\s-]*/gu, "-"); // any run holding whitespace collapses to one dash
}
