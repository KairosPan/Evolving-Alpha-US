/** The /wallet page's entry: one read of `/data/wallet.json` on load and on
 * the refresh button, like account.js. Nothing runs on a timer (charter §1:
 * nothing runs unattended) — reconcile-on-load is the server's, throttled
 * there, and happens only because the operator opened or refreshed the page. */
import { renderWallet, renderWalletError } from "./wallet-view.js";
import { readingTime } from "./account-view.js";
import { hasAlerts } from "./wallet-model.js";
import { setWalletAlert } from "./navigation.js";

const root = document.querySelector("#root");
const button = document.querySelector("#refresh");
const stamp = document.querySelector("#stamp");
const state = { detailsOpen: false };
let inflight = false;

async function load() {
  if (inflight) return;
  inflight = true;
  button.disabled = true;
  root.setAttribute("aria-busy", "true");
  // Keep the last visible snapshot and its timestamp together during a refresh.
  button.querySelector("span").textContent = "刷新中…";
  try {
    const res = await fetch("/data/wallet.json");
    let data;
    try { data = JSON.parse(await res.text()); }
    catch { throw new Error(`HTTP ${res.status} · 返回的数据无法读取`); }
    if (!res.ok || !data || data.ok !== true) throw new Error(data?.error || `HTTP ${res.status} · 钱包读取失败`);
    renderWallet(root, data, state);
    setWalletAlert(hasAlerts(data)); // this page is the one place the dot's truth is already in hand
    stamp.textContent = data.configured === true ? `更新于 ${readingTime(data.generated_at)}` : "未配置";
    stamp.title = typeof data.generated_at === "string" ? data.generated_at : "";
  } catch (err) {
    stamp.textContent = "";
    stamp.removeAttribute("title");
    renderWalletError(root, err instanceof Error ? err.message : String(err), () => void load());
  } finally {
    root.setAttribute("aria-busy", "false");
    inflight = false;
    button.disabled = false;
    button.querySelector("span").textContent = "刷新";
  }
}

button.addEventListener("click", () => void load());
void load();
