/** Read-only account dashboard. Refresh re-reads the existing cached endpoint. */
import { renderAccount, renderAccountError, readingTime } from "./account-view.js";

const root = document.querySelector("#root");
const button = document.querySelector("#refresh");
const stamp = document.querySelector("#stamp");
const state = { tab: "positions", query: "", orderFilter: "all", detailsOpen: false };
let inflight = false;

async function load() {
  if (inflight) return;
  inflight = true;
  button.disabled = true;
  root.setAttribute("aria-busy", "true");
  // Keep the last visible snapshot and its timestamp together during a refresh.
  button.querySelector("span").textContent = "刷新中…";
  try {
    const res = await fetch("/data/account.json");
    let data;
    try { data = JSON.parse(await res.text()); }
    catch { throw new Error(`HTTP ${res.status} · 返回的数据无法读取`); }
    if (!res.ok || !data || data.ok !== true) throw new Error(data?.error || `HTTP ${res.status} · 账户读取失败`);
    renderAccount(root, data, state);
    stamp.textContent = `${data.stale ? "旧数据 · " : "更新于 "}${readingTime(data.generated_at)}`;
    stamp.classList.toggle("is-stale", Boolean(data.stale));
    stamp.title = typeof data.generated_at === "string" ? data.generated_at : "";
  } catch (err) {
    stamp.textContent = "";
    stamp.classList.remove("is-stale");
    stamp.removeAttribute("title");
    renderAccountError(root, err instanceof Error ? err.message : String(err), () => void load());
  } finally {
    root.setAttribute("aria-busy", "false");
    inflight = false;
    button.disabled = false;
    button.querySelector("span").textContent = "刷新";
  }
}

button.addEventListener("click", () => void load());
void load();
