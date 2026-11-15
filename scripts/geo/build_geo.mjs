// Build Michigan geography reference files from public datasets.
//
//  * County boundaries: U.S. Census Bureau cartographic boundaries (via the `us-atlas` package).
//  * Places: GeoNames cities with population >= 1,000 (via `all-the-cities`, CC-BY 4.0).
//
// Outputs (committed so the pipeline/app never need these packages at runtime):
//  * pipeline/reference/mi_geo.json  - county FIPS -> name/region, city -> county (point-in-polygon)
//  * app/assets/mi-counties.json     - pre-projected (Albers) SVG paths for the county map
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { feature } from "topojson-client";

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..");
const cities = require("all-the-cities");
const zipcodes = require("zipcodes");
const lonlat = require("us-atlas/counties-10m.json");
const albers = require("us-atlas/counties-albers-10m.json");

// Deal Radar regions: simplified economic regions, defined by county.
const REGIONS = {
  "Southeast Michigan": ["Wayne", "Oakland", "Macomb", "Washtenaw", "Livingston", "Monroe", "St. Clair", "Lenawee"],
  "West Michigan": ["Kent", "Ottawa", "Muskegon", "Allegan", "Ionia", "Barry", "Montcalm", "Newaygo", "Oceana", "Mecosta", "Osceola", "Lake", "Mason"],
  "Southwest Michigan": ["Kalamazoo", "Berrien", "Van Buren", "Cass", "St. Joseph", "Calhoun", "Branch"],
  "Mid-Michigan": ["Ingham", "Eaton", "Clinton", "Shiawassee", "Jackson", "Hillsdale", "Gratiot", "Isabella", "Clare", "Gladwin", "Midland"],
  "East Michigan & Thumb": ["Genesee", "Saginaw", "Bay", "Lapeer", "Tuscola", "Huron", "Sanilac", "Arenac"],
  "Northern Michigan": ["Grand Traverse", "Leelanau", "Benzie", "Manistee", "Wexford", "Missaukee", "Roscommon", "Ogemaw", "Iosco", "Alcona", "Oscoda", "Crawford", "Kalkaska", "Antrim", "Charlevoix", "Emmet", "Cheboygan", "Presque Isle", "Montmorency", "Otsego", "Alpena"],
  "Upper Peninsula": ["Alger", "Baraga", "Chippewa", "Delta", "Dickinson", "Gogebic", "Houghton", "Iron", "Keweenaw", "Luce", "Mackinac", "Marquette", "Menominee", "Ontonagon", "Schoolcraft"],
};
const regionOf = {};
for (const [region, names] of Object.entries(REGIONS)) for (const n of names) regionOf[n] = region;

const isMI = (g) => String(g.id).startsWith("26");
const geo = feature(lonlat, { ...lonlat.objects.counties, geometries: lonlat.objects.counties.geometries.filter(isMI) });

function inRing(pt, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
const inPolygon = (pt, rings) => inRing(pt, rings[0]) && !rings.slice(1).some((h) => inRing(pt, h));
const contains = (f, pt) =>
  f.geometry.type === "Polygon" ? inPolygon(pt, f.geometry.coordinates) : f.geometry.coordinates.some((p) => inPolygon(pt, p));

const counties = {};
for (const f of geo.features) {
  const name = f.properties.name;
  if (!regionOf[name]) throw new Error(`County without region: ${name}`);
  counties[f.id] = { name, region: regionOf[name] };
}
if (Object.keys(counties).length !== 83) throw new Error(`Expected 83 Michigan counties, got ${Object.keys(counties).length}`);

const normalize = (s) => s.toLowerCase().replace(/\bsaint\b/g, "st").replace(/\bst\./g, "st").replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();
const cityMap = {};
let unmatched = 0;
for (const c of cities.filter((x) => x.country === "US" && x.adminCode === "MI")) {
  const pt = c.loc.coordinates;
  const county = geo.features.find((f) => contains(f, pt));
  if (!county) { unmatched++; continue; }
  const key = normalize(c.name);
  if (!cityMap[key] || c.population > cityMap[key].population) {
    cityMap[key] = { name: c.name, county: county.id, lat: +pt[1].toFixed(4), lon: +pt[0].toFixed(4), population: c.population };
  }
}

// ZIP centroids -> county; also fills small townships/villages GeoNames lacks.
const zips = {};
const zipCityVotes = {};
for (const z of Object.values(zipcodes.codes).filter((x) => x.state === "MI")) {
  const pt = [z.longitude, z.latitude];
  const county = geo.features.find((f) => contains(f, pt));
  if (!county) continue;
  zips[z.zip] = county.id;
  const key = normalize(z.city);
  (zipCityVotes[key] ??= { name: z.city, votes: {} }).votes[county.id] = (zipCityVotes[key].votes[county.id] || 0) + 1;
}
let added = 0;
for (const [key, { name, votes }] of Object.entries(zipCityVotes)) {
  if (cityMap[key]) continue;
  const ranked = Object.entries(votes).sort((a, b) => b[1] - a[1]);
  if (ranked.length > 1 && ranked[0][1] === ranked[1][1]) continue; // ambiguous: same name in two counties
  cityMap[key] = { name: name.replace(/\b\w/g, (c) => c.toUpperCase()), county: ranked[0][0], source: "zip" };
  added++;
}

fs.writeFileSync(
  path.join(root, "pipeline/reference/mi_geo.json"),
  JSON.stringify({
    sources: {
      counties: "U.S. Census Bureau cartographic boundary files (via us-atlas 3.0.1)",
      places: "GeoNames cities with population >= 1,000 (via all-the-cities 3.1.0), CC-BY 4.0",
      zips: "ZIP centroids from the zipcodes 8.0.0 package (BSD), assigned to counties by point-in-polygon",
      regions: "Michigan Deal Radar custom regions (county-based)",
    },
    counties,
    cities: cityMap,
    zips,
  }, null, 1) + "\n",
);

// Pre-projected SVG paths (Albers USA) for the county choropleth.
const proj = feature(albers, { ...albers.objects.counties, geometries: albers.objects.counties.geometries.filter(isMI) });
let [minX, minY, maxX, maxY] = [Infinity, Infinity, -Infinity, -Infinity];
const ringPath = (ring) => {
  for (const [x, y] of ring) { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
  return "M" + ring.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join("L") + "Z";
};
const shapes = proj.features.map((f) => {
  const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
  return { fips: f.id, name: f.properties.name, d: polys.map((p) => p.map(ringPath).join("")).join("") };
});
const pad = 4;
fs.mkdirSync(path.join(root, "app/assets"), { recursive: true });
fs.writeFileSync(
  path.join(root, "app/assets/mi-counties.json"),
  JSON.stringify({
    source: "U.S. Census Bureau cartographic boundaries (us-atlas), Albers USA projection",
    viewBox: [minX - pad, minY - pad, maxX - minX + 2 * pad, maxY - minY + 2 * pad].map((v) => +v.toFixed(1)),
    counties: shapes,
  }) + "\n",
);
console.log(`counties=${Object.keys(counties).length} cities=${Object.keys(cityMap).length} (+${added} from ZIP db) zips=${Object.keys(zips).length} unmatched=${unmatched}`);
