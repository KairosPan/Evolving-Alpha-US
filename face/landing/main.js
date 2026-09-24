const tabs = [...document.querySelectorAll('[role="tab"]')];
const captions = {
  strategy: "从研究假设到下一步行动，让每个想法都有清晰的上下文。",
  agents: "先让不同视角展开，再把分歧整理成值得继续验证的问题。",
  market: "把关心的资产放在一起，保留来源、币种与数据可用性的边界。",
  account: "用只读的账户视图了解资金与持仓，让研究保持全局视角。",
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
