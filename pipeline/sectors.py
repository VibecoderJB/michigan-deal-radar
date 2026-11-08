"""Map Form D industry groups and SIC codes onto one sector taxonomy."""

from __future__ import annotations

FORM_D_SECTORS = {
    "Pooled Investment Fund": "Private Funds",
    "Commercial Banking": "Financial Services",
    "Insurance": "Financial Services",
    "Investing": "Financial Services",
    "Investment Banking": "Financial Services",
    "Other Banking and Financial Services": "Financial Services",
    "Other Banking & Financial Services": "Financial Services",
    "Commercial": "Real Estate",
    "Construction": "Real Estate",
    "REITS and Finance": "Real Estate",
    "REITS & Finance": "Real Estate",
    "Residential": "Real Estate",
    "Other Real Estate": "Real Estate",
    "Biotechnology": "Health Care & Life Sciences",
    "Health Insurance": "Health Care & Life Sciences",
    "Hospitals and Physicians": "Health Care & Life Sciences",
    "Hospitals & Physicians": "Health Care & Life Sciences",
    "Pharmaceuticals": "Health Care & Life Sciences",
    "Other Health Care": "Health Care & Life Sciences",
    "Computers": "Technology",
    "Telecommunications": "Technology",
    "Other Technology": "Technology",
    "Coal Mining": "Energy & Utilities",
    "Electric Utilities": "Energy & Utilities",
    "Energy Conservation": "Energy & Utilities",
    "Environmental Services": "Energy & Utilities",
    "Oil and Gas": "Energy & Utilities",
    "Oil & Gas": "Energy & Utilities",
    "Other Energy": "Energy & Utilities",
    "Manufacturing": "Manufacturing & Automotive",
    "Retailing": "Consumer & Retail",
    "Restaurants": "Consumer & Retail",
    "Business Services": "Business Services",
    "Agriculture": "Agriculture",
    "Airlines and Airports": "Travel & Hospitality",
    "Lodging and Conventions": "Travel & Hospitality",
    "Tourism and Travel Services": "Travel & Hospitality",
    "Other Travel": "Travel & Hospitality",
    "Other": "Other",
}

# (low, high, sector, label) ranges of 4-digit SIC codes, most specific first.
SIC_RANGES = [
    (2833, 2836, "Health Care & Life Sciences", "Pharmaceuticals & Biotech"),
    (3841, 3851, "Health Care & Life Sciences", "Medical Devices"),
    (8000, 8099, "Health Care & Life Sciences", "Health Care Services"),
    (3570, 3579, "Technology", "Computer Hardware"),
    (3660, 3679, "Technology", "Electronics & Communications Equipment"),
    (7370, 7379, "Technology", "Software & IT Services"),
    (4800, 4899, "Technology", "Telecommunications"),
    (3710, 3716, "Manufacturing & Automotive", "Motor Vehicles & Parts"),
    (3714, 3714, "Manufacturing & Automotive", "Motor Vehicle Parts"),
    (4900, 4991, "Energy & Utilities", "Utilities"),
    (1000, 1499, "Energy & Utilities", "Mining & Oil/Gas"),
    (2900, 2999, "Energy & Utilities", "Petroleum Refining"),
    (6798, 6798, "Real Estate", "REIT"),
    (6500, 6553, "Real Estate", "Real Estate"),
    (6000, 6199, "Financial Services", "Banking & Credit"),
    (6200, 6299, "Financial Services", "Securities & Asset Management"),
    (6300, 6411, "Financial Services", "Insurance"),
    (6700, 6799, "Financial Services", "Holding & Investment Offices"),
    (1500, 1799, "Real Estate", "Construction"),
    (2000, 3999, "Manufacturing & Automotive", "Manufacturing"),
    (4000, 4799, "Business Services", "Transportation & Logistics"),
    (5000, 5199, "Consumer & Retail", "Wholesale Trade"),
    (5200, 5999, "Consumer & Retail", "Retail"),
    (7000, 7099, "Travel & Hospitality", "Hotels & Lodging"),
    (7000, 8999, "Business Services", "Services"),
    (100, 999, "Agriculture", "Agriculture"),
]


def sector_for_form_d(industry_group: str | None) -> str:
    return FORM_D_SECTORS.get((industry_group or "").strip(), "Other")


def sector_for_sic(sic: str | None) -> tuple[str, str | None]:
    """Return (sector, industry label) for a SIC code."""
    try:
        code = int(str(sic).strip())
    except (TypeError, ValueError):
        return "Other", None
    for low, high, sector, label in SIC_RANGES:
        if low <= code <= high:
            return sector, label
    return "Other", None
