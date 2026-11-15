// App shell: hash router, nav state, provenance popovers, watchlist stars, PWA install + offline handling.
import { loadDeals, loadMeta, status } from "./data.js";
import { date, relativeTime } from "./format.js";
import { spinner, toast } from "./ui.js";
import { renderAbout } from "./views/about.js";
import { renderActive } from "./views/active.js";
import { renderBriefing } from "./views/briefing.js";
import { renderCapital } from "./views/capital.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderDeals } from "./views/deals.js";
import { renderDetail } from "./views/detail.js";
import { renderHub } from "./views/hub.js";
import { renderLeague } from "./views/league.js";
import { renderMap } from "./views/map.js";
import { renderPrecedents } from "./views/precedents.js";
import { renderQuality } from "./views/quality.js";
import { renderSectors } from "./views/sectors.js";
import { renderSponsors } from "./views/sponsors.js";
import { renderWatchlist } from "./views/watchlist.js";
import { watchlist } from "./watchlist.js";

const main = document.getElementById("main");
const VIEWS = {
  dashboard: { title: "Dashboard", render: (r, a, p) => renderDashboard(r, p) },
  deals: { title: "Deals", render: (r, a, p) => renderDeals(r, p), selfUpdating: true },
  deal: { title: "Tear Sheet", nav: "deals", render: (r, a) => renderDetail(r, a) },
  map: { title: "County Map", render: (r, a, p) => renderMap(r, p), selfUpdating: true },
  league: { title: "League Tables", render: (r, a, p) => renderLeague(r, p), selfUpdating: true },
  precedents: { title: "Precedents", render: (r, a, p) => renderPrecedents(r, p), selfUpdating: true },
  sectors: { title: "Sector Trends", render: (r, a, p) => renderSectors(r, p), selfUpdating: true },
  sponsors: { title: "Sponsor Activity", render: (r) => renderSponsors(r) },
  active: { title: "Who's Active", render: (r, a, p) => renderActive(r, p), selfUpdating: true },
  capital: { title: "Private Capital", render: (r, a, p) => renderCapital(r, p), selfUpdating: true },
  briefing: { title: "Reports", render: (r, a) => renderBriefing(r, a) },
  watchlist: { title: "Watchlist", render: (r) => renderWatchlist(r) },
  quality: { title: "Data Quality", render: (r) => renderQuality(r) },
  about: { title: "Methodology", render: (r) => renderAbout(r) },
  analytics: { title: "Analytics", render: (r) => renderHub(r, "analytics") },
  more: { title: "More", render: (r) => renderHub(r, "more") },
};
const ANALYTICS = new Set(["map", "league", "precedents", "sectors", "sponsors"]);
const MORE = new Set(["active", "capital", "watchlist", "quality", "about"]);

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "") || "dashboard";
  const [path, query = ""] = raw.split("?");
  const [view, ...rest] = path.split("/");
  return { view: VIEWS[view] ? view : "dashboard", arg: rest.length ? decodeURIComponent(rest.join("/")) : null, params: new URLSearchParams(query) };
}

let lastRoute = "";
async function route() {
  const { view, arg, params } = parseHash();
  const def = VIEWS[view];
  const key = `${view}/${arg ?? ""}`;
  // Views that rewrite their own query string (filters) must not re-render on that change.
  if (def.selfUpdating && lastRoute === key && main.childElementCount) return;
  lastRoute = key;
  window.mdrNavDepth = (window.mdrNavDepth || 0) + 1;

  const navKey = def.nav || view;
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const n = a.dataset.nav;
    const active = n === navKey || (n === "analytics" && ANALYTICS.has(view)) || (n === "more" && MORE.has(view));
    a.classList.toggle("active", active);
    a.toggleAttribute("aria-current", active);
  });
  document.title = `${def.title} · Michigan Deal Radar`;
  main.innerHTML = spinner();
  try {
    await def.render(main, arg, params);
  } catch (err) {
    console.error(err);
    main.innerHTML = `<div class="empty"><p><strong>Couldn't load data.</strong><br>${navigator.onLine ? "Please try again in a moment." : "You're offline and this page hasn't been saved yet."}</p><button class="btn" onclick="location.reload()">Retry</button></div>`;
  }
  if (!params.toString()) window.scrollTo(0, 0);
  updateOfflineBanner();
}

document.addEventListener("click", (e) => {
  // Provenance footnotes: show the exact source text behind a value.
  const fn = e.target.closest("[data-prov]");
  if (fn) {
    e.preventDefault();
    e.stopPropagation();
    const panel = document.getElementById(fn.dataset.prov);
    const open = !panel.classList.contains("open");
    panel.classList.toggle("open", open);
    fn.setAttribute("aria-expanded", open);
    return;
  }
  const star = e.target.closest("[data-star]");
  if (star) {
    e.preventDefault();
    e.stopPropagation();
    const on = watchlist.toggle(star.dataset.star, star.dataset.name);
    document.querySelectorAll(`[data-star="${CSS.escape(star.dataset.star)}"]`).forEach((b) => {
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on);
      const label = b.querySelector("span");
      if (label) label.textContent = on ? "Watching" : "Watch";
    });
    toast(on ? `Watching ${star.dataset.name}` : `Removed ${star.dataset.name}`);
  }
}, true);

function updateOfflineBanner() {
  const banner = document.getElementById("offline-banner");
  const offline = !navigator.onLine || status.offline;
  banner.hidden = !offline;
  if (offline) banner.textContent = `Offline: showing data saved ${status.generatedAt ? relativeTime(status.generatedAt) : "earlier"}.`;
}
window.addEventListener("online", updateOfflineBanner);
window.addEventListener("offline", updateOfflineBanner);

// "Data as of" stamp: date of the most recent filing in the dataset.
Promise.all([loadMeta().catch(() => ({})), loadDeals().catch(() => null)])
  .then(([meta, dealsPayload]) => {
    status.asOf = meta.data_as_of || dealsPayload?.generatedAt?.slice(0, 10);
    const el = document.getElementById("asof");
    el.textContent = `Data as of ${date(status.asOf) || "n/a"}`;
    el.title = `Last refreshed ${relativeTime(meta.updated_at || dealsPayload?.generatedAt)}`;
    if (meta.updated_at && Date.now() - new Date(meta.updated_at).getTime() > 3 * 86400e3) el.classList.add("stale");
    document.querySelectorAll(".page-head .stamp").forEach((s) => { s.textContent = `Data as of ${date(status.asOf)}`; });
  })
  .finally(() => {
    const splash = document.getElementById("splash");
    splash?.classList.add("hide");
    setTimeout(() => splash?.remove(), 400);
  });

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
window.addEventListener("appinstalled", () => { installBtn.hidden = true; toast("Installed"); });

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch((err) => console.warn("SW registration failed", err)));
}

window.addEventListener("hashchange", route);
route();
