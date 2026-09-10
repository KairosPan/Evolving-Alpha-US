/** The same primary navigation on chat, market and account. */
const PANELS = ["strategy", "agent", "memory", "plugin"];
const marketIcon = '<svg class="rail-glyph" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true"><polyline points="2,13 6.5,8 10,10.5 16,3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><polyline points="12,3.5 16,3.5 16,7.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const accountIcon = '<svg class="rail-glyph" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true"><rect x="2" y="4.5" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11.5 9.5h4.5" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="11.8" cy="9.5" r="1" fill="currentColor"/></svg>';
const ITEMS = [
  { id: "market", href: "/market", icon: marketIcon, title: "Market" },
  { id: "strategy", href: "/#strategy", glyph: "❖", title: "Strategy — workspaces and sessions" },
  { id: "agent", href: "/#agent", glyph: "◎", title: "Agent — model, host, keys, session usage" },
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
}

mountNavigation();
