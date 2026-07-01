// Auto-scroll the thread to the newest turn after each HTMX swap.
document.body.addEventListener("htmx:afterSwap", (e) => {
  const t = document.getElementById("thread");
  if (t) t.scrollTop = t.scrollHeight;
});

// ── Agent drawer: drag-to-resize + collapse (persisted), accordions, chip flash ──
(() => {
  const cockpit = document.getElementById("cockpit");
  const drawer = document.getElementById("agent-drawer");
  const resizer = document.querySelector(".drawer-resizer");
  const WKEY = "agentDrawerW", CKEY = "agentDrawerCollapsed";

  // restore persisted width + collapsed state
  if (cockpit) {
    const w = localStorage.getItem(WKEY);
    if (w) cockpit.style.setProperty("--drawer-w", w);
  }
  if (drawer && localStorage.getItem(CKEY) === "1") drawer.classList.add("is-collapsed");

  // drag-to-resize: width = distance from the pointer to the cockpit's right edge (clamped)
  if (cockpit && resizer) {
    let dragging = false;
    resizer.addEventListener("pointerdown", (e) => {
      dragging = true; resizer.setPointerCapture(e.pointerId); e.preventDefault();
    });
    resizer.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const r = cockpit.getBoundingClientRect();
      const w = Math.max(220, Math.min(r.right - e.clientX, r.width - 320));
      const val = w + "px";
      cockpit.style.setProperty("--drawer-w", val);
      localStorage.setItem(WKEY, val);
    });
    resizer.addEventListener("pointerup", () => { dragging = false; });
    resizer.addEventListener("pointercancel", () => { dragging = false; });
  }

  // collapse toggle
  const cbtn = document.querySelector(".drawer-collapse");
  if (drawer && cbtn) {
    cbtn.addEventListener("click", () => {
      const c = drawer.classList.toggle("is-collapsed");
      localStorage.setItem(CKEY, c ? "1" : "0");
      cbtn.setAttribute("aria-expanded", c ? "false" : "true");
    });
  }

  // accordions — delegated so OOB-swapped #pending / #brain-panel keep working
  document.body.addEventListener("click", (e) => {
    const btn = e.target.closest(".acc-toggle");
    if (!btn) return;
    const acc = btn.closest(".acc");
    if (!acc) return;
    const open = acc.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });

  // chat chip → reveal + flash the drawer
  document.body.addEventListener("click", (e) => {
    const chip = e.target.closest(".change-chip[data-flash]");
    if (!chip) return;
    const d = document.getElementById(chip.getAttribute("data-flash"));
    if (!d) return;
    d.classList.remove("is-collapsed");
    localStorage.setItem(CKEY, "0");
    const cbtnChip = d.querySelector(".drawer-collapse");
    if (cbtnChip) cbtnChip.setAttribute("aria-expanded", "true");
    d.classList.remove("flash"); void d.offsetWidth; d.classList.add("flash");
  });
})();
