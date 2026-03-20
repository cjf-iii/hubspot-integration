"""Enrichment orchestrator for Cast Iron Media (CIM) prospect pipeline.

Coordinates the full enrichment flow for a HubSpot company:
  1. Read company from HubSpot (name + domain)
  2. Enrich via Apollo.io (revenue, industry, contacts)
  3. Generate AI prospect brief via LLM (Claude)
  4. Calculate CIM-specific properties (tier, vertical)
  5. Write enriched properties back to HubSpot
  6. Create contacts and associate them with the company
  7. Create a Note with the AI brief (HTML formatted)
  8. Create a review task linked to the company

This module is intentionally stateless — it takes all three clients as
arguments so callers control lifecycle management and tests can inject mocks
without monkeypatching globals.
"""

from __future__ import annotations

import re
from typing import Any

from cim.apollo import ApolloClient
from cim.hubspot import HubSpotClient
from cim.llm import generate_prospect_brief


# ---------------------------------------------------------------------------
# Tier estimation
# ---------------------------------------------------------------------------

def _estimate_tier(annual_revenue: int | float | None) -> str:
    """Estimate a CIM prospect tier from annual revenue.

    Tier is a rough proxy for prospect priority and likely ad budget. Higher
    revenue correlates with larger media spend. We return a string because
    HubSpot enumeration values are stored as strings.

    Thresholds:
      Tier 1 — $100M+ (enterprise / national brands)
      Tier 2 — $40M–$99M (large regional players)
      Tier 3 — $10M–$39M (mid-market)
      Tier 4 — <$10M or unknown (small / no data)

    Args:
        annual_revenue: Annual revenue in USD, or None if Apollo has no data.

    Returns:
        One of "1", "2", "3", "4" as a string.
    """
    if annual_revenue is None:
        # No revenue data — default to lowest priority tier
        return "4"
    if annual_revenue >= 100_000_000:
        return "1"
    if annual_revenue >= 40_000_000:
        return "2"
    if annual_revenue >= 10_000_000:
        return "3"
    return "4"


# ---------------------------------------------------------------------------
# Industry → CIM vertical mapping
# ---------------------------------------------------------------------------

# Keyword-to-vertical mapping defines which CIM vertical each industry token
# maps to. The keys are lowercase substrings to match against the normalised
# Apollo industry string. The order matters: the first match wins, so more
# specific terms should come first within any logical group.
_VERTICAL_KEYWORDS: list[tuple[str, str]] = [
    # Food & QSR group
    ("restaurant", "QSR & Fast-Casual Restaurants"),
    ("food",        "QSR & Fast-Casual Restaurants"),
    # Automotive
    ("automotive",  "Automotive Dealer Groups"),
    # Gaming & Sports Betting
    ("gambling",    "Sports Betting & Gaming"),
    ("casino",      "Sports Betting & Gaming"),
    # Tourism / Hospitality — must come before "hospital" to avoid "hospitality"
    # being swallowed by the shorter "hospital" substring match
    ("hospitality", "Tourism & Hospitality"),
    ("tourism",     "Tourism & Hospitality"),
    # Healthcare
    ("hospital",    "Healthcare Systems & Providers"),
    ("health",      "Healthcare Systems & Providers"),
    # Legal & Insurance
    ("insurance",   "Personal Injury & Legal Services"),
    ("law",         "Personal Injury & Legal Services"),
    ("legal",       "Personal Injury & Legal Services"),
    # Financial
    ("banking",     "Regional Banks & Credit Unions"),
    ("financial",   "Regional Banks & Credit Unions"),
    # Retail / Consumer
    ("retail",      "Retail Chains"),
    ("consumer",    "Retail Chains"),
    # Real Estate
    ("real estate", "Real Estate & Home Builders"),
    # Construction / Home Services
    ("construction","Home Services"),
    # Higher Education
    ("higher education", "Higher Education"),
]


def _map_vertical(industry: str | None) -> str:
    """Map an Apollo industry string to a CIM vertical label.

    Performs a case-insensitive substring search against each entry in
    _VERTICAL_KEYWORDS. Returns the first matching CIM vertical, or "Other"
    if no keyword matches. Apollo industry strings are free-form and may
    contain multiple words (e.g. "Hospital & Health Care"), so substring
    matching is more robust than exact-matching.

    Args:
        industry: Apollo's industry string, e.g. "Restaurants". May be None.

    Returns:
        A CIM vertical label string.
    """
    if not industry:
        return "Other"

    # Normalise to lowercase once so each keyword comparison is O(1)
    industry_lower = industry.lower()

    for keyword, vertical in _VERTICAL_KEYWORDS:
        if keyword in industry_lower:
            return vertical

    return "Other"


# ---------------------------------------------------------------------------
# Domain inference
# ---------------------------------------------------------------------------

def _infer_domain(name: str) -> str:
    """Infer a probable web domain from a company name.

    Lowercases the name, removes spaces and apostrophes, and appends .com.
    This is a best-effort heuristic used when HubSpot has no domain for the
    company — Apollo.io requires a domain for enrichment lookups.

    Examples:
        "Acme Corp"     → "acmecorp.com"
        "O'Brien's Pub" → "obrienspub.com"
        "Burger King"   → "burgerking.com"

    Args:
        name: Company display name from HubSpot.

    Returns:
        A lowercase .com domain string.
    """
    # Remove apostrophes and spaces; collapse any remaining whitespace
    clean = re.sub(r"[' ]", "", name.lower())
    return f"{clean}.com"


# ---------------------------------------------------------------------------
# Note body builder
# ---------------------------------------------------------------------------

def _build_note_body(
    name: str,
    tier: str,
    vertical: str,
    revenue: int | float | None,
    brief: str,
) -> str:
    """Build an HTML-formatted note body for the AI prospect brief.

    The note is stored in HubSpot's hs_note_body field, which supports HTML.
    The structure surfaces the most decision-relevant fields at the top
    (tier, vertical, spend estimate) before the full LLM-generated brief.

    Args:
        name:     Company display name for the heading.
        tier:     CIM tier string ("1" through "4").
        vertical: CIM vertical label.
        revenue:  Annual revenue in USD, or None if unavailable.
        brief:    Plain-text LLM-generated prospect brief.

    Returns:
        An HTML string suitable for storing in hs_note_body.
    """
    # Format revenue for display — plain "Unknown" if no data
    revenue_display = f"${revenue:,}" if revenue else "Unknown"

    # Wrap the LLM brief text in a paragraph, replacing newlines with <br>
    # so multi-paragraph briefs render correctly in HubSpot's note viewer.
    brief_html = brief.replace("\n", "<br>")

    return (
        f"<h3>AI Prospect Brief — {name}</h3>"
        f"<p><strong>Tier:</strong> {tier} | "
        f"<strong>Vertical:</strong> {vertical} | "
        f"<strong>Est. Annual Revenue:</strong> {revenue_display}</p>"
        f"<p>{brief_html}</p>"
    )


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def enrich_company(
    hubspot: HubSpotClient,
    apollo: ApolloClient,
    anthropic_api_key: str,
    company_id: str,
) -> dict[str, Any]:
    """Run the full CIM enrichment pipeline for a single HubSpot company.

    Orchestrates eight sequential steps:

      1. Fetch company name and domain from HubSpot.
      2. Infer domain from name if HubSpot has no domain set.
      3. Enrich via Apollo.io — firmographics (revenue, industry) + contacts.
      4. Generate a 200-300 word AI prospect brief via Claude.
      5. Calculate CIM tier (revenue-based) and vertical (industry-mapped).
      6. PATCH enriched properties back to the HubSpot company record.
      7. Create contacts and associate each with the company.
         Duplicate email errors are caught and skipped — Apollo may return
         contacts that are already in HubSpot.
      8. Create an HTML-formatted Note with the AI brief and a review Task,
         both associated with the company.

    Args:
        hubspot:          Initialised HubSpotClient (caller manages lifecycle).
        apollo:           Initialised ApolloClient (caller manages lifecycle).
        anthropic_api_key: Anthropic API key passed through to generate_prospect_brief.
        company_id:       HubSpot numeric company ID as a string.

    Returns:
        A summary dict with keys:
          - company_id:       The input company_id.
          - company_name:     Display name from HubSpot.
          - tier:             CIM tier string ("1"–"4").
          - vertical:         CIM vertical label string.
          - revenue:          Annual revenue int from Apollo, or None.
          - contacts_created: Number of contacts successfully created.
          - brief_created:    True if the AI brief note was created.
    """
    # -----------------------------------------------------------------------
    # Step 1: Read company from HubSpot
    # -----------------------------------------------------------------------
    # Fetch name and domain — these are the two fields needed to run Apollo.
    # We request them explicitly so HubSpot only returns what we need.
    company = hubspot.get_company(company_id, properties=["name", "domain"])
    props = company.get("properties", {})
    company_name: str = props.get("name") or ""
    domain: str | None = props.get("domain") or None

    # -----------------------------------------------------------------------
    # Step 2: Infer domain if not set in HubSpot
    # -----------------------------------------------------------------------
    # Apollo requires a domain for its /organizations/enrich endpoint.
    # If HubSpot has no domain, derive a best-guess from the company name.
    if not domain and company_name:
        domain = _infer_domain(company_name)

    # -----------------------------------------------------------------------
    # Step 3: Enrich via Apollo.io
    # -----------------------------------------------------------------------
    # enrich_company returns {} if Apollo has no record; find_contacts returns []
    # if no matching people are found. Both are treated as empty data, not errors.
    apollo_data: dict = {}
    contacts: list[dict] = []
    if domain:
        apollo_data = apollo.enrich_company(domain)
        contacts = apollo.find_contacts(domain)

    # Extract the two Apollo fields we derive CIM properties from
    annual_revenue = apollo_data.get("annual_revenue")
    industry = apollo_data.get("industry")

    # -----------------------------------------------------------------------
    # Step 4: Generate AI prospect brief
    # -----------------------------------------------------------------------
    brief = generate_prospect_brief(
        api_key=anthropic_api_key,
        company_name=company_name,
        company_data=apollo_data,
        contacts=contacts,
    )

    # -----------------------------------------------------------------------
    # Step 5: Calculate CIM-specific properties
    # -----------------------------------------------------------------------
    tier = _estimate_tier(annual_revenue)
    vertical = _map_vertical(industry)

    # -----------------------------------------------------------------------
    # Step 6: Write enriched properties back to HubSpot
    # -----------------------------------------------------------------------
    # Store tier, vertical, and the raw revenue/industry from Apollo so HubSpot
    # becomes the system of record for all enrichment results.
    enriched_props: dict[str, Any] = {
        "cim_tier": tier,
        "cim_vertical": vertical,
    }
    # Only write optional fields when Apollo actually returned data — avoids
    # overwriting existing values with empty strings on re-enrichment runs.
    if annual_revenue is not None:
        enriched_props["annualrevenue"] = str(annual_revenue)
    if industry:
        enriched_props["industry"] = industry

    hubspot.update_company(company_id, enriched_props)

    # -----------------------------------------------------------------------
    # Step 7: Create contacts and associate with company
    # -----------------------------------------------------------------------
    # Apollo may return contacts whose email is already in HubSpot (duplicate),
    # which causes a 409 / HTTPStatusError. We catch per-contact so a single
    # duplicate does not abort the entire enrichment run.
    contacts_created = 0
    for contact in contacts:
        try:
            contact_record = hubspot.create_contact(
                {
                    "firstname": contact.get("first_name") or "",
                    "lastname": contact.get("last_name") or "",
                    "jobtitle": contact.get("title") or "",
                    "email": contact.get("email") or "",
                    # Associate by storing company name; the HubSpot UI will link
                    # via the explicit association call below.
                    "company": company_name,
                }
            )
            # Associate the new contact with this company so they appear on the
            # company's Contacts tab in HubSpot.
            hubspot._associate("contacts", contact_record["id"], "companies", company_id)
            contacts_created += 1
        except Exception:
            # Duplicate email (409) or other transient error — skip and continue.
            # We don't re-raise because partial contact creation is better than
            # aborting the whole pipeline for one existing record.
            pass

    # -----------------------------------------------------------------------
    # Step 8a: Create HTML note with AI brief
    # -----------------------------------------------------------------------
    note_body = _build_note_body(
        name=company_name,
        tier=tier,
        vertical=vertical,
        revenue=annual_revenue,
        brief=brief,
    )
    hubspot.create_note(note_body, company_id=company_id)
    brief_created = True

    # -----------------------------------------------------------------------
    # Step 8b: Create review task linked to the company
    # -----------------------------------------------------------------------
    hubspot.create_task(
        subject=f"Review AI brief: {company_name}",
        body=(
            f"Enrichment pipeline completed for {company_name}. "
            f"Tier {tier} | {vertical}. Review the AI brief note and prepare outreach."
        ),
        company_id=company_id,
    )

    return {
        "company_id": company_id,
        "company_name": company_name,
        "tier": tier,
        "vertical": vertical,
        "revenue": annual_revenue,
        "contacts_created": contacts_created,
        "brief_created": brief_created,
    }
