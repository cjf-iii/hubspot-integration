"""LLM-powered prospect brief generator for Cast Iron Media (CIM).

Generates a 200-300 word sales intelligence brief for a prospect company
by calling Claude with CIM-specific context injected into the system
prompt. The brief helps CIM sales reps quickly understand how a prospect
aligns with CIM's inventory, verticals, and DMA footprint before outreach.

CIM context used in prompts:
  - CIM is a sports-focused CTV/OTT ad tech company
  - Operates in 13 DMAs where regional sports network (RSN) disruption
    has created new premium sports inventory
  - Key advertiser verticals: Sports Betting, Auto Dealers, QSR,
    PI & Legal, Healthcare, Banks, Retail, Tourism, Home Services,
    Higher Education
  - Tiers 1-4 represent prospect priority (1 = highest strategic fit)
"""

import anthropic


# The model ID to use for brief generation. claude-sonnet-4-20250514 balances
# quality and cost for high-volume enrichment runs.
_MODEL = "claude-sonnet-4-20250514"

# System prompt injecting CIM's business context so the LLM can reason about
# vertical alignment, DMA coverage, and tier assignment without needing that
# context re-explained in every user message.
_SYSTEM_PROMPT = """\
You are a sales intelligence analyst for Cast Iron Media (CIM), a sports-focused \
Connected TV (CTV) and Over-The-Top (OTT) advertising technology company.

CIM CONTEXT:
- CIM operates premium sports ad inventory in 13 DMAs (Designated Market Areas) \
where Regional Sports Network (RSN) disruption has created new, underserved \
sports-viewing inventory on streaming platforms.
- CIM's core value proposition: reach sports fans in their DMA with targeted, \
measurable CTV/OTT ads — filling the gap left by declining RSN cable bundles.
- CIM's key advertiser verticals (in priority order):
  1. Sports Betting — high-value, sports-contextual alignment
  2. Auto Dealers — high local spend, sports audience overlap
  3. QSR (Quick Service Restaurants) — mass reach, local franchise budgets
  4. PI & Legal (Personal Injury / Law Firms) — aggressive TV spenders
  5. Healthcare — strong local brand need in DMA markets
  6. Banks & Financial Services — local branch advertising
  7. Retail — seasonal high-spend, DMA-level targeting
  8. Tourism & Hospitality — destination marketing in sports markets
  9. Home Services — local service area matches DMA footprint
  10. Higher Education — student recruitment in sports markets

TIER DEFINITIONS (assign one to each prospect):
  Tier 1: Perfect fit — operates in CIM verticals, high local/regional ad spend, \
sports-contextual brand
  Tier 2: Strong fit — in a core vertical, some regional/local presence, \
likely CTV budget
  Tier 3: Moderate fit — adjacent vertical or national brand with local co-op potential
  Tier 4: Long-shot — outside core verticals but may have opportunistic budget

Your briefs should be direct, data-grounded, and actionable for a sales rep \
preparing for a first call.\
"""


def generate_prospect_brief(
    api_key: str,
    company_name: str,
    company_data: dict,
    contacts: list[dict],
) -> str:
    """Generate a CIM sales prospect brief using Claude.

    Builds a structured prompt from enrichment data and calls the Anthropic
    Messages API synchronously. Returns the brief as a plain text string.

    The brief covers:
      - Company overview (what they do, size, location)
      - CIM vertical and DMA alignment analysis
      - Media buying behaviour inference
      - Recommended outreach approach
      - Prospect tier assignment (1-4)

    Args:
        api_key:      Anthropic API key for authenticating the request.
        company_name: Display name of the prospect company.
        company_data: Dict of firmographic fields — expected keys: industry,
                      annual_revenue, estimated_employees, city, state.
                      Any key may be None/missing; the prompt handles gaps.
        contacts:     List of contact dicts with keys: first_name, last_name,
                      title, email. Used to personalise outreach suggestions.

    Returns:
        A 200-300 word prospect brief as a plain text string.

    Raises:
        anthropic.APIError: If the Anthropic API returns an error response.
    """
    # Build a human-readable summary of firmographic data for the prompt.
    # Handle None/missing values gracefully so sparse Apollo data doesn't
    # cause the LLM to see "None" literals in the prompt.
    industry = company_data.get("industry") or "Unknown industry"
    revenue = company_data.get("annual_revenue")
    employees = company_data.get("estimated_employees")
    city = company_data.get("city") or "Unknown city"
    state = company_data.get("state") or "Unknown state"

    # Format revenue as a human-readable figure when available
    revenue_str = f"${revenue:,}" if revenue else "Unknown"
    employees_str = str(employees) if employees else "Unknown"

    # Format contacts list for the prompt — show name, title, email
    if contacts:
        contacts_lines = "\n".join(
            f"  - {c.get('first_name', '')} {c.get('last_name', '')} "
            f"({c.get('title', 'Unknown title')}) — {c.get('email') or 'email not available'}"
            for c in contacts
        )
    else:
        contacts_lines = "  No contacts found."

    # Compose the user message with all available enrichment data.
    # Structured sections make it easy for the LLM to extract each data point
    # without needing to parse ambiguous prose.
    user_message = f"""\
Generate a prospect brief for: {company_name}

COMPANY DATA:
  Industry: {industry}
  Annual Revenue: {revenue_str}
  Estimated Employees: {employees_str}
  Location: {city}, {state}

KEY CONTACTS:
{contacts_lines}

Write a 200-300 word prospect brief covering:
1. Company overview — what they do, scale, and market position
2. CIM vertical and DMA alignment — which CIM vertical they fit and why, \
and whether their location/market overlaps with CIM's 13-DMA footprint
3. Media buying behaviour — inferred from industry, size, and vertical
4. Recommended approach — how CIM should position the pitch, which contacts \
to target first, and what CIM value props to lead with
5. Tier assignment — assign Tier 1-4 with a one-sentence rationale

Format: plain text paragraphs, no markdown, no bullet points in the output.\
"""

    # Initialise a fresh Anthropic client per call. This function is designed
    # to be called at the task/enrichment level where the caller provides the
    # key — it does not hold a persistent connection, keeping the function
    # stateless and easy to test by mocking the Anthropic class.
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract the text from the first content block. Claude's response will
    # always have at least one TextBlock when not using tool_use.
    return message.content[0].text
