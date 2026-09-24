const tabs = [...document.querySelectorAll('[role="tab"]')];
const captions = {
  strategy:
    "Keep the hypothesis, evidence and next step in one research context.",
  agents:
    "Compare perspectives, then turn disagreements into questions to test.",
  market:
    "Follow assets together, with source, currency and coverage kept in view.",
  account: "Keep cash and positions in context with a read-only account view.",
};

function selectTab(tab, moveFocus = false) {
  for (const candidate of tabs) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", String(selected));
    candidate.tabIndex = selected ? 0 : -1;
    document.getElementById(candidate.getAttribute("aria-controls")).hidden =
      !selected;
  }
  for (const item of document.querySelectorAll("[data-sidebar]")) {
    item.classList.toggle("active", item.dataset.sidebar === tab.dataset.view);
  }
  document.getElementById("demo-caption").textContent =
    captions[tab.dataset.view];
  if (moveFocus) tab.focus();
}

for (const [index, tab] of tabs.entries()) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft")
      next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    selectTab(tabs[next], true);
  });
}
