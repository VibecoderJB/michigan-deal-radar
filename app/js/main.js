// App shell: hash router, navigation state, watchlist stars, PWA install + offline handling.
import { loadDeals, status } from "./data.js";
import { relativeTime } from "./format.js";
import { spinner, toast } from "./ui.js";
import { renderAbout } from "./views/about.js";
import { renderBriefing } from "./views/briefing.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderDeals } from "./views/deals.js";
import { renderDetail } from "./views/detail.js";
import { renderWatchlist } from "./views/watchlist.js";
import { watchlist } from "./watchlist.js";

const main = document.getElementById("main");
const TITLES = { dashboard: "Dashboard", deals: "Deals", deal: "Deal", briefing: "Weekly Briefing", watchlist: "Watchlist", about: "About" };

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "") || "dashboard";
  const [path, query = ""] = raw.split("?");
  const [view, ...rest] = path.split("/");
  return { view, arg: rest.length ? decodeURIComponent(rest.join("/")) : null, params: new URLSearchParams(query) };
}

let lastRoute = "";
async function route() {
  const { view, arg, params } = parseHash();
  const routeKey = `${view}/${arg ?? ""}`;
  // The deals view rewrites its own query string; don't re-render (and lose focus) for that.
  if (view === "deals" && lastRoute === routeKey && main.childElementCount) return;
  lastRoute = routeKey;
  window.mdrNavDepth = (window.mdrNavDepth || 0) + 1; // lets "Back" links use history when possible

  document.querySelectorAll("[data-nav]").forEach((a) => {
    const active = a.dataset.nav === view || (view === "deal" && a.dataset.nav === "deals");
    a.classList.toggle("active", active);
    a.toggleAttribute("aria-current", active);
  });
  document.title = `${TITLES[view] || "Michigan Deal Radar"} · Michigan Deal Radar`;
  main.innerHTML = spinner();

  try {
    switch (view) {
      case "deals": await renderDeals(main, params); break;
      case "deal": await renderDetail(main, arg); break;
      case "briefing": await renderBriefing(main, arg); break;
      case "watchlist": await renderWatchlist(main); break;
      case "about": await renderAbout(main); break;
      default: await renderDashboard(main);
    }
  } catch (err) {
    console.error(err);
    main.innerHTML = `<div class="empty"><p><strong>Couldn't load data.</strong><br>${navigator.onLine ? "Please try again in a moment." : "You're offline and this page hasn't been saved yet."}</p><button class="btn" onclick="location.reload()">Retry</button></div>`;
  }
  if (view !== "deals" || !params.toString()) window.scrollTo(0, 0);
  updateOfflineBanner();
}

// Star buttons anywhere in the app.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-star]");
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  const on = watchlist.toggle(btn.dataset.star, btn.dataset.name);
  document.querySelectorAll(`[data-star="${CSS.escape(btn.dataset.star)}"]`).forEach((b) => {
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on);
    b.setAttribute("aria-label", `${on ? "Remove from" : "Add to"} watchlist`);
    const label = b.querySelector("span");
    if (label) label.textContent = on ? "Watching" : "Watch";
  });
  toast(on ? `Watching ${btn.dataset.name}` : `Removed ${btn.dataset.name}`);
});

function updateOfflineBanner() {
  const banner = document.getElementById("offline-banner");
  const offline = !navigator.onLine || status.offline;
  banner.hidden = !offline;
  if (offline) banner.textContent = `Offline: showing data saved ${status.generatedAt ? relativeTime(status.generatedAt) : "earlier"}.`;
}
window.addEventListener("online", updateOfflineBanner);
window.addEventListener("offline", updateOfflineBanner);

// Freshness indicator in the top bar.
loadDeals()
  .then(({ generatedAt }) => {
    const el = document.getElementById("freshness");
    el.textContent = `Updated ${relativeTime(generatedAt)}`;
    el.title = `Data generated ${new Date(generatedAt).toLocaleString()}`;
    if (Date.now() - new Date(generatedAt).getTime() > 3 * 86400e3) el.classList.add("stale");
  })
  .catch(() => {})
  .finally(() => {
    const splash = document.getElementById("splash");
    splash.classList.add("hide");
    setTimeout(() => splash.remove(), 400);
  });

// PWA install prompt (Chrome/Edge/Android). iOS uses Share → Add to Home Screen.
let deferredPrompt;
const installBtn = document.getElementById("install-btn");
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  installBtn.hidden = false;
});
installBtn.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  installBtn.hidden = true;
});
window.addEventListener("appinstalled", () => {
  installBtn.hidden = true;
  toast("Installed. Find Deal Radar on your home screen.");
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch((err) => console.warn("SW registration failed", err)));
}

window.addEventListener("hashchange", route);
route();
