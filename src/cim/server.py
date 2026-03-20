"""Lightweight web server for the CIM enrichment UI.

Serves a single-page frontend and exposes one API endpoint that wraps
the enrichment pipeline. Designed to be dead simple: `cim serve` starts
everything, open the browser, type a company name, watch it enrich.

Runs in two modes:
  - LIVE MODE: When API keys are configured in .env, uses real APIs
  - DEMO MODE: When no keys are present, uses realistic mock data
    so the full experience works out of the box with zero configuration.

Uses FastAPI + uvicorn for minimal overhead. The /enrich endpoint
streams Server-Sent Events so the frontend can show pipeline progress
in real time rather than waiting for the full result.
"""

import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse

# Path to the visual/ directory containing app.html
VISUAL_DIR = Path(__file__).resolve().parent.parent.parent / "visual"

app = FastAPI(title="CIM HubSpot Enrichment", docs_url=None, redoc_url=None)


def _is_demo_mode() -> bool:
    """Check if we should run in demo mode (no API keys configured)."""
    return not all(os.getenv(k) for k in ("HUBSPOT_API_KEY", "ANTHROPIC_API_KEY", "APOLLO_API_KEY"))


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/")
async def index():
    """Serve the frontend."""
    return FileResponse(VISUAL_DIR / "app.html")


@app.get("/api/mode")
async def mode():
    """Return current operating mode so the UI can display a badge."""
    return {"mode": "demo" if _is_demo_mode() else "live"}


@app.get("/api/enrich")
async def enrich_endpoint(name: str = Query(..., description="Company name to enrich")):
    """Enrich a company and stream progress via Server-Sent Events.

    In demo mode, uses mock data with realistic delays to simulate
    the full pipeline. In live mode, calls real APIs.
    """

    if _is_demo_mode():
        return StreamingResponse(
            _demo_enrichment(name),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _live_enrichment(name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _demo_enrichment(name: str):
    """Simulated enrichment using mock data — no API keys required.

    Adds realistic delays between steps to simulate the actual pipeline
    timing. Uses curated mock data for known companies (Culver's,
    Discount Tire, BetRivers, D.R. Horton) and generates plausible
    profiles for any other company name.
    """
    from cim.demo_data import get_mock_data

    mock = get_mock_data(name)
    apollo_data = mock["apollo"]
    contacts = mock["contacts"]

    # Step 1: "Create" in HubSpot (simulated)
    yield _sse("step", {"step": 1, "label": "Creating company in HubSpot...", "status": "active"})
    time.sleep(0.8)
    company_id = f"demo-{abs(hash(name)) % 100000}"
    yield _sse("step", {"step": 1, "label": "Company created", "status": "done"})

    # Step 2: "Apollo" enrichment (simulated)
    yield _sse("step", {"step": 2, "label": "Querying Apollo.io...", "status": "active"})
    time.sleep(1.5)
    yield _sse("step", {
        "step": 2,
        "label": f"Found {len(contacts)} contacts",
        "status": "done",
        "data": {
            "industry": apollo_data.get("industry", "Unknown"),
            "revenue": apollo_data.get("annual_revenue"),
            "employees": apollo_data.get("estimated_employees"),
            "contacts": [
                {"name": f"{c['first_name']} {c['last_name']}", "title": c["title"]}
                for c in contacts
            ],
        },
    })

    # Step 3: "AI brief" generation (simulated)
    yield _sse("step", {"step": 3, "label": "Generating AI prospect brief...", "status": "active"})
    time.sleep(2.5)
    yield _sse("step", {
        "step": 3,
        "label": "Brief generated",
        "status": "done",
        "data": {"brief_preview": mock["brief"][:200] + "..."},
    })

    # Step 4: "Writeback" to HubSpot (simulated)
    yield _sse("step", {"step": 4, "label": "Writing to HubSpot...", "status": "active"})
    time.sleep(1.0)
    yield _sse("step", {"step": 4, "label": "Enrichment complete", "status": "done"})

    # Final result
    yield _sse("result", {
        "company_name": apollo_data.get("name", name),
        "company_id": company_id,
        "tier": mock["tier"],
        "vertical": mock["vertical"],
        "revenue": apollo_data.get("annual_revenue"),
        "contacts_created": len(contacts),
        "brief": mock["brief"],
    })


def _live_enrichment(name: str):
    """Real enrichment using live APIs — requires configured API keys."""
    try:
        from cim.config import load_config
        from cim.hubspot import HubSpotClient
        from cim.apollo import ApolloClient
        from cim.llm import generate_prospect_brief
        from cim.enrichment import enrich_company

        config = load_config()
        hs = HubSpotClient(api_key=config.hubspot_api_key)
        apollo = ApolloClient(api_key=config.apollo_api_key)

        # Step 1: Create company in HubSpot
        yield _sse("step", {"step": 1, "label": "Creating company in HubSpot...", "status": "active"})
        results = hs.search_companies(name)
        if results:
            company_id = results[0]["id"]
            yield _sse("step", {"step": 1, "label": "Found existing company", "status": "done"})
        else:
            created = hs.create_company({"name": name})
            company_id = created["id"]
            yield _sse("step", {"step": 1, "label": "Company created", "status": "done"})

        # Step 2: Apollo enrichment
        yield _sse("step", {"step": 2, "label": "Querying Apollo.io...", "status": "active"})
        apollo_data = apollo.enrich_company(
            name.lower().replace(" ", "").replace("'", "") + ".com"
        )
        contacts = apollo.find_contacts(
            name.lower().replace(" ", "").replace("'", "") + ".com", limit=3
        )
        yield _sse("step", {
            "step": 2,
            "label": f"Found {len(contacts)} contacts",
            "status": "done",
            "data": {
                "industry": apollo_data.get("industry", "Unknown"),
                "revenue": apollo_data.get("annual_revenue"),
                "employees": apollo_data.get("estimated_employees"),
                "contacts": [
                    {"name": f"{c.get('first_name', '')} {c.get('last_name', '')}", "title": c.get("title", "")}
                    for c in contacts
                ],
            },
        })

        # Step 3: Generate AI brief
        yield _sse("step", {"step": 3, "label": "Generating AI prospect brief...", "status": "active"})
        brief = generate_prospect_brief(
            api_key=config.anthropic_api_key,
            company_name=name,
            company_data=apollo_data,
            contacts=contacts,
        )
        yield _sse("step", {"step": 3, "label": "Brief generated", "status": "done"})

        # Step 4: Write to HubSpot
        yield _sse("step", {"step": 4, "label": "Writing to HubSpot...", "status": "active"})
        result = enrich_company(
            hubspot=hs,
            apollo=apollo,
            anthropic_api_key=config.anthropic_api_key,
            company_id=company_id,
        )
        yield _sse("step", {"step": 4, "label": "Enrichment complete", "status": "done"})

        # Final result
        yield _sse("result", {
            "company_name": result["company_name"],
            "company_id": result["company_id"],
            "tier": result["tier"],
            "vertical": result["vertical"],
            "revenue": result["revenue"],
            "contacts_created": result["contacts_created"],
            "brief": brief,
        })

        hs.close()
        apollo.close()

    except Exception as e:
        yield _sse("error", {"message": str(e)})
