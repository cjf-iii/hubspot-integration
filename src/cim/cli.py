"""CIM CLI — command-line interface for Cast Iron Media HubSpot enrichment.

Provides three top-level commands:

  cim setup   — Creates CIM custom property groups and properties in HubSpot.
                Safe to re-run; 409 Conflict responses are treated as success
                (idempotent). Run once per HubSpot portal before using enrich.

  cim enrich  — Enriches a single company via Apollo + LLM and writes results
                back to HubSpot. Accepts either --id (direct HubSpot company ID)
                or --name (searches HubSpot; creates if not found).

  cim demo    — Full end-to-end demonstration: creates a company, runs the
                full enrichment pipeline, and displays formatted results.
                Designed for first-run validation and sales demos.

  cim serve   — Launches the web UI on localhost:8000. Open the browser,
                type a company name, watch enrichment happen in real time.

All commands load API keys from the environment via load_config(), which reads
a .env file if present. Missing keys produce a clear error before any API calls
are attempted.

Entry point registered in pyproject.toml as `cim = "cim.cli:cli"`.
"""

import click

from cim.apollo import ApolloClient
from cim.config import load_config
from cim.enrichment import enrich_company
from cim.hubspot import HubSpotClient


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """Cast Iron Media HubSpot enrichment CLI.

    Use 'cim COMMAND --help' for details on each subcommand.
    """
    # The group itself has no logic — it exists solely as a namespace for the
    # three subcommands. Click handles dispatch automatically.


# ---------------------------------------------------------------------------
# cim setup
# ---------------------------------------------------------------------------

@cli.command()
def setup() -> None:
    """Create CIM custom property groups and properties in HubSpot.

    Creates two property groups and their associated custom fields:

      cim_intelligence (on companies):
        - cim_tier           (enumeration 1–4)
        - sports_alignment_score (number)
        - cim_vertical       (enumeration, all CIM verticals)

      cim_deal_tracking (on deals):
        - io_status          (enumeration: draft/sent/signed/active/completed)
        - campaign_type      (enumeration: ctv_programmatic/sponsorship/custom_package)
        - cpm_rate           (number)
        - impressions_committed (number)

    Safe to re-run — existing groups and properties produce a 409 which is
    treated as success, so this command is idempotent.
    """
    # Load API keys — raises ValueError with a clear message if any are missing
    config = load_config()

    with HubSpotClient(api_key=config.hubspot_api_key) as hs:

        # ----------------------------------------------------------------
        # Company property group: cim_intelligence
        # ----------------------------------------------------------------
        click.echo("Creating property group: cim_intelligence (companies)...")
        hs.create_property_group(
            object_type="companies",
            name="cim_intelligence",
            label="CIM Intelligence",
        )
        click.echo("  done.")

        # Company properties — all grouped under cim_intelligence
        # Each dict follows the HubSpot property definition schema:
        # name, label, type, fieldType, groupName, and optional options list
        company_props = [
            {
                # Tier 1–4 mirrors the revenue-based tier logic in enrichment.py.
                # Stored as enumeration so HubSpot UI shows a dropdown selector.
                "name": "cim_tier",
                "label": "CIM Tier",
                "type": "enumeration",
                "fieldType": "select",
                "groupName": "cim_intelligence",
                "options": [
                    {"label": "Tier 1 — Enterprise", "value": "1", "displayOrder": 1},
                    {"label": "Tier 2 — Large Regional", "value": "2", "displayOrder": 2},
                    {"label": "Tier 3 — Mid-Market", "value": "3", "displayOrder": 3},
                    {"label": "Tier 4 — Small / Unqualified", "value": "4", "displayOrder": 4},
                ],
            },
            {
                # Numeric score (0–100) representing sports audience alignment.
                # Currently assigned manually; future enrichment could auto-score.
                "name": "sports_alignment_score",
                "label": "Sports Alignment Score",
                "type": "number",
                "fieldType": "number",
                "groupName": "cim_intelligence",
            },
            {
                # CIM verticals mapped from Apollo industry data. The full set
                # of verticals is defined in enrichment.py's _VERTICAL_KEYWORDS.
                "name": "cim_vertical",
                "label": "CIM Vertical",
                "type": "enumeration",
                "fieldType": "select",
                "groupName": "cim_intelligence",
                "options": [
                    {"label": "QSR & Fast-Casual Restaurants",     "value": "QSR & Fast-Casual Restaurants",     "displayOrder": 1},
                    {"label": "Automotive Dealer Groups",          "value": "Automotive Dealer Groups",          "displayOrder": 2},
                    {"label": "Sports Betting & Gaming",           "value": "Sports Betting & Gaming",           "displayOrder": 3},
                    {"label": "Healthcare Systems & Providers",    "value": "Healthcare Systems & Providers",    "displayOrder": 4},
                    {"label": "Personal Injury & Legal Services",  "value": "Personal Injury & Legal Services",  "displayOrder": 5},
                    {"label": "Regional Banks & Credit Unions",    "value": "Regional Banks & Credit Unions",    "displayOrder": 6},
                    {"label": "Retail Chains",                     "value": "Retail Chains",                     "displayOrder": 7},
                    {"label": "Tourism & Hospitality",             "value": "Tourism & Hospitality",             "displayOrder": 8},
                    {"label": "Real Estate & Home Builders",       "value": "Real Estate & Home Builders",       "displayOrder": 9},
                    {"label": "Home Services",                     "value": "Home Services",                     "displayOrder": 10},
                    {"label": "Higher Education",                  "value": "Higher Education",                  "displayOrder": 11},
                    {"label": "Other",                             "value": "Other",                             "displayOrder": 12},
                ],
            },
        ]

        click.echo("Creating company properties (cim_tier, sports_alignment_score, cim_vertical)...")
        hs.create_properties("companies", company_props)
        click.echo("  done.")

        # ----------------------------------------------------------------
        # Deal property group: cim_deal_tracking
        # ----------------------------------------------------------------
        click.echo("Creating property group: cim_deal_tracking (deals)...")
        hs.create_property_group(
            object_type="deals",
            name="cim_deal_tracking",
            label="CIM Deal Tracking",
        )
        click.echo("  done.")

        # Deal properties — track IO lifecycle and campaign parameters
        deal_props = [
            {
                # IO status tracks the insertion order lifecycle from draft
                # through completion — mirrors the standard CIM sales process.
                "name": "io_status",
                "label": "IO Status",
                "type": "enumeration",
                "fieldType": "select",
                "groupName": "cim_deal_tracking",
                "options": [
                    {"label": "Draft",     "value": "draft",     "displayOrder": 1},
                    {"label": "Sent",      "value": "sent",      "displayOrder": 2},
                    {"label": "Signed",    "value": "signed",    "displayOrder": 3},
                    {"label": "Active",    "value": "active",    "displayOrder": 4},
                    {"label": "Completed", "value": "completed", "displayOrder": 5},
                ],
            },
            {
                # Campaign type distinguishes CIM's three core product lines.
                # Affects pricing, creative requirements, and reporting cadence.
                "name": "campaign_type",
                "label": "Campaign Type",
                "type": "enumeration",
                "fieldType": "select",
                "groupName": "cim_deal_tracking",
                "options": [
                    {"label": "CTV Programmatic",  "value": "ctv_programmatic",  "displayOrder": 1},
                    {"label": "Sponsorship",        "value": "sponsorship",       "displayOrder": 2},
                    {"label": "Custom Package",     "value": "custom_package",    "displayOrder": 3},
                ],
            },
            {
                # CPM rate in USD. Stored as a number so HubSpot can run
                # calculations and revenue forecasting against it.
                "name": "cpm_rate",
                "label": "CPM Rate ($)",
                "type": "number",
                "fieldType": "number",
                "groupName": "cim_deal_tracking",
            },
            {
                # Total impressions committed in the IO. Combined with cpm_rate
                # this drives the deal value calculation: revenue = impressions / 1000 * CPM.
                "name": "impressions_committed",
                "label": "Impressions Committed",
                "type": "number",
                "fieldType": "number",
                "groupName": "cim_deal_tracking",
            },
        ]

        click.echo("Creating deal properties (io_status, campaign_type, cpm_rate, impressions_committed)...")
        hs.create_properties("deals", deal_props)
        click.echo("  done.")

    click.echo("\nSetup complete. All CIM properties are ready in HubSpot.")


# ---------------------------------------------------------------------------
# cim enrich
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--id",
    "company_id",
    default=None,
    help="HubSpot company ID to enrich directly.",
)
@click.option(
    "--name",
    "company_name",
    default=None,
    help="Company name to search for (creates if not found).",
)
def enrich(company_id: str | None, company_name: str | None) -> None:
    """Enrich a company via Apollo + LLM and write results to HubSpot.

    Requires exactly one of --id or --name.

    \b
    Examples:
      cim enrich --id 12345678
      cim enrich --name "Burger King"
    """
    # Validate that exactly one lookup strategy was provided
    if not company_id and not company_name:
        raise click.UsageError("Provide either --id or --name.")
    if company_id and company_name:
        raise click.UsageError("Provide either --id or --name, not both.")

    config = load_config()

    with HubSpotClient(api_key=config.hubspot_api_key) as hs:
        apollo = ApolloClient(api_key=config.apollo_api_key)

        try:
            # ----------------------------------------------------------------
            # Resolve company_id from name if --name was given
            # ----------------------------------------------------------------
            if company_name and not company_id:
                click.echo(f"Searching HubSpot for '{company_name}'...")
                results = hs.search_companies(company_name)

                if results:
                    # Use the first search result — CONTAINS_TOKEN returns
                    # the closest match first for partial name queries.
                    company_id = results[0]["id"]
                    found_name = results[0].get("properties", {}).get("name", company_name)
                    click.echo(f"  Found: {found_name} (id={company_id})")
                else:
                    # Company not in HubSpot — create a stub record so
                    # enrichment has a real ID to work with.
                    click.echo(f"  Not found — creating new company '{company_name}'...")
                    created = hs.create_company({"name": company_name})
                    company_id = created["id"]
                    click.echo(f"  Created with id={company_id}")

            # ----------------------------------------------------------------
            # Run the enrichment pipeline
            # ----------------------------------------------------------------
            click.echo(f"\nEnriching company id={company_id}...")
            result = enrich_company(
                hubspot=hs,
                apollo=apollo,
                anthropic_api_key=config.anthropic_api_key,
                company_id=company_id,
            )

            # ----------------------------------------------------------------
            # Display formatted results
            # ----------------------------------------------------------------
            click.echo("\nEnrichment complete:")
            click.echo(f"  Company:          {result['company_name']}")
            click.echo(f"  HubSpot ID:       {result['company_id']}")
            click.echo(f"  Tier:             {result['tier']}")
            click.echo(f"  Vertical:         {result['vertical']}")
            revenue = result["revenue"]
            click.echo(f"  Revenue:          {'${:,}'.format(revenue) if revenue else 'Unknown'}")
            click.echo(f"  Contacts created: {result['contacts_created']}")
            click.echo(f"  AI brief note:    {'created' if result['brief_created'] else 'skipped'}")

        finally:
            # Always close the Apollo client even if enrichment raises —
            # HubSpotClient is closed by the 'with' block above.
            apollo.close()


# ---------------------------------------------------------------------------
# cim demo
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("company_name")
def demo(company_name: str) -> None:
    """Run a full demo enrichment flow for COMPANY_NAME.

    Creates the company in HubSpot, runs the complete enrichment pipeline
    (Apollo → LLM → HubSpot write-back), then displays formatted results.
    Designed for first-run validation and live sales demonstrations.

    \b
    Example:
      cim demo "Burger King"
    """
    config = load_config()

    click.echo(f"\nCIM Enrichment Demo — {company_name}")
    click.echo("=" * 50)

    with HubSpotClient(api_key=config.hubspot_api_key) as hs:
        apollo = ApolloClient(api_key=config.apollo_api_key)

        try:
            # ----------------------------------------------------------------
            # Step 1: Create company in HubSpot
            # ----------------------------------------------------------------
            click.echo(f"\n[1/4] Creating company '{company_name}' in HubSpot...")
            created = hs.create_company({"name": company_name})
            company_id = created["id"]
            click.echo(f"      Created with id={company_id}")

            # ----------------------------------------------------------------
            # Step 2: Apollo enrichment
            # ----------------------------------------------------------------
            click.echo("\n[2/4] Fetching firmographic data from Apollo.io...")
            # enrich_company handles this internally; we show the step label
            # here so the demo output makes the pipeline stages visible.
            click.echo("      Querying Apollo for revenue, industry, and contacts...")

            # ----------------------------------------------------------------
            # Step 3: LLM brief generation
            # ----------------------------------------------------------------
            click.echo("\n[3/4] Generating AI prospect brief via Claude...")
            click.echo("      Sending enrichment data to Claude for analysis...")

            # ----------------------------------------------------------------
            # Step 4: Write back to HubSpot (runs all four steps internally)
            # ----------------------------------------------------------------
            click.echo("\n[4/4] Running full enrichment pipeline and writing to HubSpot...")
            result = enrich_company(
                hubspot=hs,
                apollo=apollo,
                anthropic_api_key=config.anthropic_api_key,
                company_id=company_id,
            )

            # ----------------------------------------------------------------
            # Display results
            # ----------------------------------------------------------------
            click.echo("\n" + "=" * 50)
            click.echo("Demo Results:")
            click.echo("=" * 50)
            click.echo(f"  Company:          {result['company_name']}")
            click.echo(f"  HubSpot ID:       {result['company_id']}")
            click.echo(f"  Tier:             {result['tier']}")
            click.echo(f"  Vertical:         {result['vertical']}")
            revenue = result["revenue"]
            click.echo(f"  Revenue:          {'${:,}'.format(revenue) if revenue else 'Unknown'}")
            click.echo(f"  Contacts created: {result['contacts_created']}")
            click.echo(f"  AI brief note:    {'created' if result['brief_created'] else 'skipped'}")
            click.echo("=" * 50)
            click.echo("\nDemo complete. View the company in HubSpot to see the full brief and task.")

        finally:
            # Always close Apollo client — HubSpotClient is closed by 'with' block
            apollo.close()


# ---------------------------------------------------------------------------
# serve command — web UI
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--port", default=8000, help="Port to serve on (default: 8000)")
@click.option("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
def serve(port: int, host: str) -> None:
    """Launch the web UI for interactive enrichment.

    Opens a browser-based interface where you can type a company name
    and watch the enrichment pipeline run in real time with SSE progress.

    Requires: pip install uvicorn fastapi
    """
    try:
        import uvicorn
    except ImportError:
        click.echo("Error: uvicorn and fastapi are required for the web UI.")
        click.echo("Install them: pip install uvicorn fastapi")
        raise SystemExit(1)

    click.echo(f"\n  CIM Enrichment UI starting on http://{host}:{port}")
    click.echo("  Press Ctrl+C to stop.\n")

    uvicorn.run("cim.server:app", host=host, port=port, log_level="warning")
