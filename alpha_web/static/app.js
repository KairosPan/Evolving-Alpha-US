// Filtering is server-rendered via HTMX (hx-get -> list partial); chip state comes back in the
// markup. This file stays intentionally tiny — a small affordance so a slow swap reads as "working".
document.body.addEventListener("htmx:beforeRequest", (e) => {
  const list = document.getElementById(e.detail.target && e.detail.target.id);
  if (list) list.style.opacity = "0.5";
});
document.body.addEventListener("htmx:afterSwap", (e) => {
  if (e.detail.target) e.detail.target.style.opacity = "";
});

// Cockpit loading-state affordance: disable submitting button while a request is pending
document.body.addEventListener('htmx:beforeRequest', (e) => {
  const btn = e.detail.elt.querySelector('button[type=submit]') || e.detail.elt;
  if (btn && btn.tagName === 'BUTTON') btn.disabled = true;
});
document.body.addEventListener('htmx:afterRequest', (e) => {
  const btn = e.detail.elt.querySelector('button[type=submit]') || e.detail.elt;
  if (btn && btn.tagName === 'BUTTON') btn.disabled = false;
});

// Brain drawer: toggle the rail accordion open/closed without navigating.
document.querySelectorAll(".nav-group-toggle").forEach((btn) => {
  btn.addEventListener("click", () => {
    const group = btn.closest(".nav-group");
    const open = group.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
});
