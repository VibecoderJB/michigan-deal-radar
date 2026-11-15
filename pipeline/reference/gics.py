"""Approximate GICS classification and Michigan focus sectors.

GICS is a proprietary MSCI/S&P taxonomy; official codes are not published for private
companies. We map the classification each filing *does* carry (SEC SIC code or the
Form D industry group) to the closest GICS sector and sub-industry. The mapping is
labelled "mapped from SIC xxxx" / "mapped from Form D industry group" in the data so
it is never mistaken for an official assignment.
"""

from __future__ import annotations

# (low, high, sector, sub-industry) over 4-digit SIC codes. First match wins, so
# specific ranges come before broad ones.
SIC_TO_GICS: list[tuple[int, int, str, str]] = [
    (100, 999, "Consumer Staples", "Agricultural Products & Services"),
    (1000, 1099, "Materials", "Diversified Metals & Mining"),
    (1311, 1311, "Energy", "Oil & Gas Exploration & Production"),
    (1381, 1389, "Energy", "Oil & Gas Equipment & Services"),
    (1400, 1499, "Materials", "Construction Materials"),
    (1531, 1531, "Consumer Discretionary", "Homebuilding"),
    (1500, 1799, "Industrials", "Construction & Engineering"),
    (2080, 2089, "Consumer Staples", "Beverages"),
    (2000, 2099, "Consumer Staples", "Packaged Foods & Meats"),
    (2100, 2199, "Consumer Staples", "Tobacco"),
    (2200, 2399, "Consumer Discretionary", "Apparel, Accessories & Luxury Goods"),
    (2400, 2499, "Industrials", "Building Products"),
    (2520, 2599, "Industrials", "Office Services & Supplies"),
    (2500, 2519, "Consumer Discretionary", "Home Furnishings"),
    (2600, 2699, "Materials", "Paper & Plastic Packaging Products & Materials"),
    (2700, 2799, "Communication Services", "Publishing"),
    (2836, 2836, "Health Care", "Biotechnology"),
    (2833, 2835, "Health Care", "Pharmaceuticals"),
    (2840, 2844, "Consumer Staples", "Household Products"),
    (2800, 2899, "Materials", "Specialty Chemicals"),
    (2900, 2999, "Energy", "Oil & Gas Refining & Marketing"),
    (3010, 3011, "Consumer Discretionary", "Tires & Rubber"),
    (3000, 3099, "Materials", "Paper & Plastic Packaging Products & Materials"),
    (3100, 3199, "Consumer Discretionary", "Footwear"),
    (3200, 3299, "Materials", "Construction Materials"),
    (3300, 3399, "Materials", "Steel"),
    (3400, 3499, "Industrials", "Industrial Machinery & Supplies & Components"),
    (3523, 3524, "Industrials", "Agricultural & Farm Machinery"),
    (3530, 3537, "Industrials", "Construction Machinery & Heavy Transportation Equipment"),
    (3570, 3579, "Information Technology", "Technology Hardware, Storage & Peripherals"),
    (3500, 3599, "Industrials", "Industrial Machinery & Supplies & Components"),
    (3630, 3639, "Consumer Discretionary", "Household Appliances"),
    (3651, 3651, "Consumer Discretionary", "Consumer Electronics"),
    (3660, 3669, "Information Technology", "Communications Equipment"),
    (3674, 3674, "Information Technology", "Semiconductors"),
    (3670, 3679, "Information Technology", "Electronic Components"),
    (3600, 3699, "Industrials", "Electrical Components & Equipment"),
    (3711, 3711, "Consumer Discretionary", "Automobile Manufacturers"),
    (3713, 3713, "Industrials", "Construction Machinery & Heavy Transportation Equipment"),
    (3710, 3716, "Consumer Discretionary", "Automotive Parts & Equipment"),
    (3720, 3729, "Industrials", "Aerospace & Defense"),
    (3760, 3769, "Industrials", "Aerospace & Defense"),
    (3730, 3743, "Industrials", "Construction Machinery & Heavy Transportation Equipment"),
    (3750, 3751, "Consumer Discretionary", "Motorcycle Manufacturers"),
    (3790, 3799, "Consumer Discretionary", "Leisure Products"),
    (3840, 3842, "Health Care", "Health Care Equipment"),
    (3843, 3851, "Health Care", "Health Care Supplies"),
    (3800, 3873, "Information Technology", "Electronic Equipment & Instruments"),
    (3900, 3999, "Consumer Discretionary", "Leisure Products"),
    (4000, 4099, "Industrials", "Rail Transportation"),
    (4100, 4199, "Industrials", "Passenger Ground Transportation"),
    (4200, 4299, "Industrials", "Cargo Ground Transportation"),
    (4400, 4499, "Industrials", "Marine Transportation"),
    (4512, 4512, "Industrials", "Passenger Airlines"),
    (4500, 4599, "Industrials", "Air Freight & Logistics"),
    (4700, 4799, "Industrials", "Air Freight & Logistics"),
    (4830, 4841, "Communication Services", "Cable & Satellite"),
    (4800, 4899, "Communication Services", "Integrated Telecommunication Services"),
    (4922, 4925, "Utilities", "Gas Utilities"),
    (4930, 4939, "Utilities", "Multi-Utilities"),
    (4940, 4941, "Utilities", "Water Utilities"),
    (4950, 4959, "Industrials", "Environmental & Facilities Services"),
    (4900, 4999, "Utilities", "Electric Utilities"),
    (5122, 5122, "Health Care", "Health Care Distributors"),
    (5140, 5149, "Consumer Staples", "Food Distributors"),
    (5000, 5199, "Industrials", "Trading Companies & Distributors"),
    (5200, 5299, "Consumer Discretionary", "Home Improvement Retail"),
    (5300, 5399, "Consumer Staples", "Consumer Staples Merchandise Retail"),
    (5400, 5499, "Consumer Staples", "Food Retail"),
    (5500, 5599, "Consumer Discretionary", "Automotive Retail"),
    (5600, 5699, "Consumer Discretionary", "Apparel Retail"),
    (5700, 5799, "Consumer Discretionary", "Home Furnishing Retail"),
    (5810, 5813, "Consumer Discretionary", "Restaurants"),
    (5912, 5912, "Consumer Staples", "Drug Retail"),
    (5900, 5999, "Consumer Discretionary", "Other Specialty Retail"),
    (6020, 6036, "Financials", "Regional Banks"),
    (6141, 6141, "Financials", "Consumer Finance"),
    (6162, 6163, "Financials", "Commercial & Residential Mortgage Finance"),
    (6099, 6199, "Financials", "Consumer Finance"),
    (6282, 6282, "Financials", "Asset Management & Custody Banks"),
    (6200, 6299, "Financials", "Investment Banking & Brokerage"),
    (6311, 6311, "Financials", "Life & Health Insurance"),
    (6321, 6324, "Health Care", "Managed Health Care"),
    (6411, 6411, "Financials", "Insurance Brokers"),
    (6300, 6399, "Financials", "Property & Casualty Insurance"),
    (6500, 6553, "Real Estate", "Real Estate Operating Companies"),
    (6770, 6770, "Financials", "Blank Check / SPAC"),
    (6798, 6798, "Real Estate", "REITs"),
    (6700, 6799, "Financials", "Asset Management & Custody Banks"),
    (7000, 7099, "Consumer Discretionary", "Hotels, Resorts & Cruise Lines"),
    (7200, 7299, "Consumer Discretionary", "Specialized Consumer Services"),
    (7311, 7319, "Communication Services", "Advertising"),
    (7361, 7363, "Industrials", "Human Resource & Employment Services"),
    (7372, 7372, "Information Technology", "Application Software"),
    (7370, 7379, "Information Technology", "IT Consulting & Other Services"),
    (7300, 7399, "Industrials", "Diversified Support Services"),
    (7500, 7549, "Consumer Discretionary", "Specialized Consumer Services"),
    (7990, 7997, "Consumer Discretionary", "Leisure Facilities"),
    (7800, 7999, "Communication Services", "Movies & Entertainment"),
    (8060, 8069, "Health Care", "Health Care Facilities"),
    (8000, 8099, "Health Care", "Health Care Services"),
    (8200, 8299, "Consumer Discretionary", "Education Services"),
    (8711, 8711, "Industrials", "Construction & Engineering"),
    (8731, 8731, "Health Care", "Life Sciences Tools & Services"),
    (8700, 8799, "Industrials", "Research & Consulting Services"),
]

FORM_D_TO_GICS: dict[str, tuple[str, str]] = {
    "Agriculture": ("Consumer Staples", "Agricultural Products & Services"),
    "Commercial Banking": ("Financials", "Regional Banks"),
    "Insurance": ("Financials", "Property & Casualty Insurance"),
    "Investing": ("Financials", "Asset Management & Custody Banks"),
    "Investment Banking": ("Financials", "Investment Banking & Brokerage"),
    "Pooled Investment Fund": ("Financials", "Asset Management & Custody Banks"),
    "Other Banking and Financial Services": ("Financials", "Diversified Financial Services"),
    "Business Services": ("Industrials", "Diversified Support Services"),
    "Coal Mining": ("Energy", "Coal & Consumable Fuels"),
    "Electric Utilities": ("Utilities", "Electric Utilities"),
    "Energy Conservation": ("Industrials", "Electrical Components & Equipment"),
    "Environmental Services": ("Industrials", "Environmental & Facilities Services"),
    "Oil and Gas": ("Energy", "Oil & Gas Exploration & Production"),
    "Other Energy": ("Energy", "Oil & Gas Equipment & Services"),
    "Biotechnology": ("Health Care", "Biotechnology"),
    "Health Insurance": ("Health Care", "Managed Health Care"),
    "Hospitals and Physicians": ("Health Care", "Health Care Facilities"),
    "Pharmaceuticals": ("Health Care", "Pharmaceuticals"),
    "Other Health Care": ("Health Care", "Health Care Services"),
    "Manufacturing": ("Industrials", "Industrial Machinery & Supplies & Components"),
    "Commercial": ("Real Estate", "Real Estate Operating Companies"),
    "Construction": ("Industrials", "Construction & Engineering"),
    "REITS and Finance": ("Real Estate", "REITs"),
    "Residential": ("Real Estate", "Real Estate Development"),
    "Other Real Estate": ("Real Estate", "Real Estate Operating Companies"),
    "Retailing": ("Consumer Discretionary", "Other Specialty Retail"),
    "Restaurants": ("Consumer Discretionary", "Restaurants"),
    "Computers": ("Information Technology", "Technology Hardware, Storage & Peripherals"),
    "Telecommunications": ("Communication Services", "Integrated Telecommunication Services"),
    "Other Technology": ("Information Technology", "Software"),
    "Airlines and Airports": ("Industrials", "Passenger Airlines"),
    "Lodging and Conventions": ("Consumer Discretionary", "Hotels, Resorts & Cruise Lines"),
    "Tourism and Travel Services": ("Consumer Discretionary", "Leisure Facilities"),
    "Other Travel": ("Consumer Discretionary", "Hotels, Resorts & Cruise Lines"),
}

REAL_ESTATE_FORM_D = {"Commercial", "Residential", "REITS and Finance", "Other Real Estate", "Construction"}

FOCUS_SECTORS = (
    "Automotive & Mobility",
    "Advanced Manufacturing",
    "Healthcare",
    "Software & Technology",
    "Consumer",
    "Business Services",
    "Financial Services",
    "Real Estate",
    "Energy & Utilities",
)
_AUTO = {
    "Automobile Manufacturers", "Automotive Parts & Equipment", "Tires & Rubber", "Automotive Retail",
    "Motorcycle Manufacturers",
}
_BUSINESS_SERVICES = {
    "Diversified Support Services", "Human Resource & Employment Services", "Research & Consulting Services",
    "Environmental & Facilities Services", "Cargo Ground Transportation", "Air Freight & Logistics",
    "Trading Companies & Distributors", "Construction & Engineering", "Advertising", "Rail Transportation",
    "Marine Transportation", "Passenger Ground Transportation",
}


def from_sic(sic: str | int | None) -> tuple[str, str] | None:
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return None
    for low, high, sector, sub in SIC_TO_GICS:
        if low <= code <= high:
            return sector, sub
    return None


def from_form_d(industry_group: str | None) -> tuple[str, str] | None:
    return FORM_D_TO_GICS.get((industry_group or "").strip())


def focus_sector(gics_sector: str | None, sub_industry: str | None) -> str | None:
    """Collapse GICS into the Michigan focus sectors used for trend analysis."""
    if not gics_sector:
        return None
    if sub_industry in _AUTO:
        return "Automotive & Mobility"
    if gics_sector == "Health Care":
        return "Healthcare"
    if gics_sector in ("Information Technology", "Communication Services"):
        return "Software & Technology"
    if sub_industry in _BUSINESS_SERVICES:
        return "Business Services"
    if gics_sector in ("Industrials", "Materials"):
        return "Advanced Manufacturing"
    if gics_sector in ("Consumer Discretionary", "Consumer Staples"):
        return "Consumer"
    if gics_sector == "Financials":
        return "Financial Services"
    if gics_sector == "Real Estate":
        return "Real Estate"
    if gics_sector in ("Energy", "Utilities"):
        return "Energy & Utilities"
    return None
