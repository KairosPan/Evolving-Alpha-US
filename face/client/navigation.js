/** The same primary navigation on chat, market, account and wallet. */
import { hasAlerts } from "./wallet-model.js";

const PANELS = ["strategy", "agent", "memory", "plugin"];
const marketIcon = '<svg class="rail-glyph" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true"><polyline points="2,13 6.5,8 10,10.5 16,3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><polyline points="12,3.5 16,3.5 16,7.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const walletIcon = '<svg class="rail-glyph" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true"><rect x="2" y="4.5" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M2 8h14" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11.5h3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
const accountIcon = '<svg class="rail-glyph" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true"><rect x="2" y="4.5" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11.5 9.5h4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="11.8" cy="9.5" r="1" fill="currentColor"/></svg>';
/* Order is the intro page's (docs/design/kairos-intro.html): the wallet sits
 * right after agent — money next to the agent that spends it — and account
 * stays pinned at the foot (`rail-account`, keyed on the id below). */
const ITEMS = [
  { id: "market", href: "/market", icon: marketIcon, title: "Market" },
  { id: "strategy", href: "/#strategy", glyph: "❖", title: "Strategy — workspaces and sessions" },
  { id: "agent", href: "/#agent", glyph: "◎", title: "Agent — model, host, keys, session usage" },
  { id: "wallet", href: "/wallet", icon: walletIcon, title: "Wallet — the agent's USDC budgets and payments" },
  { id: "memory", href: "/#memory", glyph: "▤", title: "Memory — the skill packs Kairos carries" },
  { id: "plugin", href: "/#plugin", glyph: "⚙", title: "Plugin — composed rows and MCP tools" },
  { id: "account", href: "/account", icon: accountIcon, title: "Account" },
];

/** Only the four known chat panels can be addressed by a fragment. */
export function panelFromHash(hash) {
  const name = hash.replace(/^#/, "");
  return PANELS.includes(name) ? name : "strategy";
}

export function setNavigationActive(name) {
  for (const link of document.querySelectorAll("[data-navigation] .rail-btn")) {
    const active = link.dataset.nav === name;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

/** The wallet item's dot (spec §2: "shows a dot while an alert stands").
 * The wallet page sets it from the payload it already has; every other page
 * reads `/data/wallet.json` once at mount (below). A wallet that is not
 * configured, or a read that fails, shows nothing — the dot means "an alert
 * stands", never "the page could not tell".
 * @param {boolean} on */
export function setWalletAlert(on) {
  const link = document.querySelector('[data-navigation] .rail-btn[data-nav="wallet"]');
  if (!(link instanceof HTMLElement)) return;
  link.classList.toggle("has-alert", on === true);
  link.title = on === true ? "Wallet — an alert stands" : "Wallet — the agent's USDC budgets and payments";
}

function mountNavigation() {
  const rail = document.querySelector("[data-navigation]");
  if (!rail) return;
  for (const item of ITEMS) {
    const link = document.createElement("a");
    link.className = `rail-btn${item.id === "account" ? " rail-account" : ""}`;
    link.href = item.href;
    link.title = item.title;
    link.setAttribute("aria-label", item.id[0].toUpperCase() + item.id.slice(1));
    link.dataset.nav = item.id;
    if (PANELS.includes(item.id)) link.dataset.panel = item.id;
    // Icon markup is a fixed local constant; no data enters HTML parsing.
    if (item.icon) link.innerHTML = item.icon;
    else {
      const glyph = document.createElement("span");
      glyph.className = "rail-glyph";
      glyph.textContent = item.glyph;
      glyph.setAttribute("aria-hidden", "true");
      link.append(glyph);
    }
    const label = document.createElement("span");
    label.className = "rail-label";
    label.textContent = item.id;
    link.append(label);
    rail.append(link);
  }
  setNavigationActive(rail.dataset.navigation === "chat" ? panelFromHash(location.hash) : rail.dataset.navigation);
  /* The dot, from one read. Not on the wallet page (its own load owns the
   * truth and calls `setWalletAlert`), and swallow-and-degrade everywhere
   * else: a missing route (the server side lands later) is no alert. */
  if (rail.dataset.navigation !== "wallet") {
    fetch("/data/wallet.json").then((res) => res.ok ? res.json() : null).then((body) => {
      setWalletAlert(body?.ok === true && body.configured === true && hasAlerts(body));
    }).catch(() => { /* no dot */ });
  }
}

mountNavigation();
