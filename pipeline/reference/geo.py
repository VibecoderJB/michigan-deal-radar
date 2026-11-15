"""Michigan geography: city/ZIP -> county -> Deal Radar region.

Reference data is built by ``scripts/geo/build_geo.mjs`` from public datasets
(Census county boundaries, GeoNames places, a ZIP centroid database) and committed
as ``mi_geo.json``. Every lookup returns the method used so the UI can show provenance.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

GEO_FILE = Path(__file__).with_name("mi_geo.json")
CENSUS_COUNTIES_URL = "https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html"

REGIONS = (
    "Southeast Michigan",
    "West Michigan",
    "Southwest Michigan",
    "Mid-Michigan",
    "East Michigan & Thumb",
    "Northern Michigan",
    "Upper Peninsula",
)


@dataclass(frozen=True)
class Location:
    city: str
    county: str  # e.g. "Kent County"
    county_fips: str
    region: str
    method: str  # "city", "city (fuzzy)", "zip"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(GEO_FILE.read_text(encoding="utf-8"))


def normalize_city(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"\b(charter\s+)?(township|twp\.?)\b", "", s)
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\bst\.", "st", s)
    s = re.sub(r"\bmt\.?\s", "mount ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def county_info(fips: str) -> tuple[str, str]:
    c = _data()["counties"][fips]
    return f"{c['name']} County", c["region"]


def locate(city: str | None, zip_code: str | None = None) -> Location | None:
    """Resolve a Michigan city (and optional ZIP) to county and region."""
    data = _data()
    if city:
        key = normalize_city(city)
        hit = data["cities"].get(key)
        method = "city"
        if hit is None and key:
            close = difflib.get_close_matches(key, data["cities"].keys(), n=1, cutoff=0.92)
            if close:
                hit, method = data["cities"][close[0]], "city (fuzzy)"
        if hit:
            county, region = county_info(hit["county"])
            return Location(hit["name"], county, hit["county"], region, method)
    if zip_code:
        fips = data["zips"].get(str(zip_code)[:5])
        if fips:
            county, region = county_info(fips)
            return Location(city or "", county, fips, region, "zip")
    return None


def all_counties() -> dict[str, dict]:
    return _data()["counties"]
