// Mobile hub pages that group the sidebar sections behind the 5-tab bottom bar.
import { pageHead } from "../ui.js";

const HUBS = {
  analytics: {
    title: "Analytics",
    links: [
      ["#/map", "County Map", "Deal activity by Michigan county and region"],
      ["#/league", "League Tables", "Most active acquirers, sponsors and advisors"],
      ["#/precedents", "Precedent Transactions", "Disclosed values and multiples, median and mean"],
      ["#/sectors", "Sector Trends", "Quarter-over-quarter and year-over-year by sector"],
      ["#/sponsors", "Sponsor Activity", "PE platform deals vs. add-ons"],
    ],
  },
  more: {
    title: "More",
    links: [
      ["#/active", "Who's Active in Michigan", "Banks, PE firms and law firms on Michigan deals"],
      ["#/capital", "Private Capital", "Fund raises (Form D) and 13D stakes"],
      ["#/watchlist", "Watchlist", "Companies you follow"],
      ["#/quality", "Data Quality", "Latest pipeline run report"],
      ["#/about", "About & Methodology", "Sources, verification and limitations"],
    ],
  },
};

export function renderHub(root, which) {
  const hub = HUBS[which] || HUBS.more;
  root.innerHTML = `${pageHead(hub.title, "")}<div class="hub">${hub.links.map(([href, t, d]) => `<a href="${href}"><strong>${t}</strong><span>${d}</span></a>`).join("")}</div>`;
}
