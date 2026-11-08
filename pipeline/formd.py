"""Parser for Form D (Regulation D private placement notices) XML."""

from __future__ import annotations

from .xmlutil import ParseError, parse_xml, text, to_bool, to_number

# Federal exemption codes used on Form D, translated for display.
EXEMPTIONS = {
    "06b": "Rule 506(b)",
    "06c": "Rule 506(c)",
    "04": "Rule 504",
    "04a": "Rule 504(b)(1)(i)",
    "04b": "Rule 504(b)(1)(ii)",
    "04c": "Rule 504(b)(1)(iii)",
    "3C": "Investment Company Act 3(c)",
    "3C.1": "ICA 3(c)(1)",
    "3C.7": "ICA 3(c)(7)",
    "06": "Rule 506",
    "4a5": "Securities Act 4(a)(5)",
}

SECURITY_FLAGS = {
    "isEquityType": "Equity",
    "isDebtType": "Debt",
    "isOptionToAcquireType": "Options/Warrants",
    "isSecurityToBeAcquiredType": "Security to be Acquired",
    "isPooledInvestmentFundType": "Pooled Fund Interests",
    "isTenantInCommonType": "Tenant-in-Common",
    "isMineralPropertyType": "Mineral Property",
}


def parse_form_d(xml_text: str) -> dict:
    """Extract the fields the app needs from a Form D ``primary_doc.xml``."""
    root = parse_xml(xml_text)
    if root.tag != "edgarSubmission":
        raise ParseError(f"unexpected root element <{root.tag}>")

    issuer = root.find("primaryIssuer")
    if issuer is None:
        raise ParseError("Form D has no <primaryIssuer>")
    offering = root.find("offeringData")
    if offering is None:
        raise ParseError("Form D has no <offeringData>")

    address = issuer.find("issuerAddress")
    industry_group = offering.find("industryGroup")
    fund_info = industry_group.find("investmentFundInfo") if industry_group is not None else None
    fund_type = text(fund_info, "investmentFundType")
    industry = text(industry_group, "industryGroupType")

    first_sale = offering.find("typeOfFiling/dateOfFirstSale")
    sales = offering.find("offeringSalesAmounts")
    total_offering_raw = text(sales, "totalOfferingAmount")

    securities_el = offering.find("typesOfSecuritiesOffered")
    securities = []
    if securities_el is not None:
        for flag, label in SECURITY_FLAGS.items():
            if to_bool(text(securities_el, flag)):
                securities.append(label)
        other = text(securities_el, "descriptionOfOtherType")
        if to_bool(text(securities_el, "isOtherType")) and other:
            securities.append(other)

    exemptions = [
        EXEMPTIONS.get(item.text.strip(), item.text.strip())
        for item in offering.findall("federalExemptionsExclusions/item")
        if item.text and item.text.strip()
    ]

    return {
        "cik": text(issuer, "cik"),
        "issuer_name": text(issuer, "entityName"),
        "city": (text(address, "city") or "").title() or None,
        "state": text(address, "stateOrCountry"),
        "zip": text(address, "zipCode"),
        "entity_type": text(issuer, "entityType"),
        "jurisdiction": (text(issuer, "jurisdictionOfInc") or "").title() or None,
        "year_of_inc": text(issuer, "yearOfInc/value"),
        "industry": industry,
        "is_pooled_fund": industry == "Pooled Investment Fund" or fund_type is not None,
        "fund_type": fund_type,
        "revenue_range": text(offering, "issuerSize/revenueRange"),
        "is_amendment": bool(to_bool(text(offering, "typeOfFiling/newOrAmendment/isAmendment"))),
        "date_of_first_sale": text(first_sale, "value"),
        "first_sale_yet_to_occur": bool(to_bool(text(first_sale, "yetToOccur"))),
        "more_than_one_year": bool(to_bool(text(offering, "durationOfOffering/moreThanOneYear"))),
        "is_business_combination": bool(
            to_bool(text(offering, "businessCombinationTransaction/isBusinessCombinationTransaction"))
        ),
        "securities": securities,
        "exemptions": exemptions,
        "minimum_investment": to_number(text(offering, "minimumInvestmentAccepted")),
        "total_offering_amount": to_number(total_offering_raw),
        "offering_indefinite": (total_offering_raw or "").strip().lower() == "indefinite",
        "total_amount_sold": to_number(text(sales, "totalAmountSold")),
        "total_remaining": to_number(text(sales, "totalRemaining")),
        "investor_count": to_number(text(offering, "investors/totalNumberAlreadyInvested")),
        "has_non_accredited": bool(to_bool(text(offering, "investors/hasNonAccreditedInvestors"))),
        "sales_commissions": to_number(text(offering, "salesCommissionsFindersFees/salesCommissions/dollarAmount")),
        "related_persons": _related_persons(root),
        "signature_date": text(offering, "signatureBlock/signature/signatureDate"),
    }


def _related_persons(root) -> list[dict]:
    people = []
    for person in root.findall("relatedPersonsList/relatedPersonInfo"):
        first = text(person, "relatedPersonName/firstName", "")
        middle = text(person, "relatedPersonName/middleName", "")
        last = text(person, "relatedPersonName/lastName", "")
        name = " ".join(p for p in (first, middle, last) if p and p not in {"-", "N/A"})
        if not name:
            continue
        roles = [
            r.text.strip()
            for r in person.findall("relatedPersonRelationshipList/relationship")
            if r.text and r.text.strip()
        ]
        people.append(
            {
                "name": name,
                "roles": roles,
                "clarification": text(person, "relationshipClarification"),
            }
        )
    return people
