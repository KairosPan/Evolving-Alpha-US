// Auto-scroll the thread to the newest turn after each HTMX swap.
document.body.addEventListener("htmx:afterSwap", (e) => {
  const t = document.getElementById("thread");
  if (t) t.scrollTop = t.scrollHeight;
});
