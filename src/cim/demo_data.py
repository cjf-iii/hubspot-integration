"""Mock data for demo mode — runs without any API keys.

When API keys aren't configured, the enrichment pipeline uses this
simulated data to show the full experience. Every company name gets
realistic, CIM-relevant mock data so the demo feels real.

The data is intentionally detailed — this is a sales demo, not a
placeholder. Each mock response mirrors the exact structure that
Apollo.io and Claude would return.
"""

import time
import random

# Realistic prospect database keyed by lowercase company name.
# Falls back to a generated profile for unknown companies.
MOCK_COMPANIES: dict[str, dict] = {
    "culver's": {
        "apollo": {
            "name": "Culver's",
            "industry": "Restaurants",
            "annual_revenue": 65_000_000,
            "estimated_employees": 400,
            "city": "Prairie du Sac",
            "state": "Wisconsin",
        },
        "contacts": [
            {"first_name": "Jane", "last_name": "Smith", "title": "VP Marketing", "email": "jane.smith@culvers.com"},
            {"first_name": "Michael", "last_name": "Chen", "title": "Media Director", "email": "michael.chen@culvers.com"},
        ],
        "brief": (
            "Culver's is a Midwest-dominant QSR chain with an estimated $65M in annual advertising, "
            "heavily weighted toward broadcast and local spot buys across their 900+ locations. "
            "They're active in 8 CIM priority markets — Detroit, Cleveland, Tampa, Minneapolis, "
            "St. Louis, Milwaukee, Kansas City, and Cincinnati — all of which have teams in RSN transition.\n\n"
            "Their target demographic (M25-54, families) maps directly to live sports audiences, "
            "and Culver's has a history of local sports sponsorships in Wisconsin and the Midwest. "
            "The RSN collapse creates an opportunity to position CIM's DMA-targeted CTV inventory "
            "as a natural migration path from their existing local broadcast buys.\n\n"
            "Recommended approach: Lead with the multi-market efficiency story. One IO activates "
            "all 8 DMAs simultaneously — something their current local broadcast buying process "
            "can't do. Reference the Tigers, Guardians, and Brewers streaming transitions as "
            "proof points for new inventory availability.\n\n"
            "Tier 2 classification: $65M spend with strong sports alignment across 8 CIM markets. "
            "Regional footprint with multi-DMA activation potential makes this a high-value target "
            "for CIM's cross-market campaign capability."
        ),
        "tier": "2",
        "vertical": "QSR & Fast-Casual Restaurants",
    },
    "discount tire": {
        "apollo": {
            "name": "Discount Tire",
            "industry": "Retail",
            "annual_revenue": 125_000_000,
            "estimated_employees": 850,
            "city": "Scottsdale",
            "state": "Arizona",
        },
        "contacts": [
            {"first_name": "Robert", "last_name": "Garcia", "title": "CMO", "email": "robert.garcia@discounttire.com"},
            {"first_name": "Sarah", "last_name": "Kim", "title": "VP Advertising", "email": "sarah.kim@discounttire.com"},
            {"first_name": "David", "last_name": "Torres", "title": "Media Buyer", "email": "david.torres@discounttire.com"},
        ],
        "brief": (
            "Discount Tire is one of the largest independent tire retailers in the US with an "
            "estimated $125M annual ad spend, primarily allocated to broadcast TV, digital, and "
            "local sponsorships. With 1,100+ locations across 36 states, they have significant "
            "presence in 11 of CIM's 13 priority DMAs.\n\n"
            "Their advertising strategy targets the M25-54 demographic — a near-perfect overlap "
            "with live sports audiences. Discount Tire has existing sponsorship deals with "
            "NASCAR, IndyCar, and several MLB teams, demonstrating strong sports advertising "
            "alignment and comfort with sports-adjacent inventory.\n\n"
            "The RSN disruption creates a unique opportunity: as local sports move to streaming, "
            "Discount Tire's existing local TV sports adjacencies become fragmented. CIM can "
            "consolidate their multi-market sports reach through a single programmatic CTV buy "
            "with guaranteed delivery — replacing the complexity of 11 separate local buys.\n\n"
            "Tier 1 classification: $125M spend, 11-market coverage, proven sports advertiser "
            "with existing team sponsorships. This is a cross-regional account that should be "
            "prioritized for executive-level outreach."
        ),
        "tier": "1",
        "vertical": "Retail Chains",
    },
    "betrivers": {
        "apollo": {
            "name": "BetRivers / Rush Street Interactive",
            "industry": "Gambling & Casinos",
            "annual_revenue": 75_000_000,
            "estimated_employees": 320,
            "city": "Chicago",
            "state": "Illinois",
        },
        "contacts": [
            {"first_name": "Amanda", "last_name": "Park", "title": "VP Marketing", "email": "amanda.park@rushstreetinteractive.com"},
            {"first_name": "Chris", "last_name": "Williams", "title": "Head of Media", "email": "chris.williams@rushstreetinteractive.com"},
        ],
        "brief": (
            "Rush Street Interactive (BetRivers, PlaySugarHouse) is a top-6 US online sports "
            "betting operator with an estimated $75M annual advertising budget. They operate "
            "in 15 states with legal online sports betting, including all 13 CIM priority DMAs "
            "except markets where betting is pending.\n\n"
            "Sports betting operators are CIM's highest-value vertical: they require DMA-level "
            "geo-targeting (betting ads must only run in legal states), high-frequency placement "
            "during live sports, and real-time creative swaps for odds and promotions. Traditional "
            "national CTV buys waste budget on non-legal markets. CIM's market-by-market approach "
            "eliminates this waste entirely.\n\n"
            "BetRivers differentiates on the 'local bettor' positioning — they sponsor local "
            "teams and emphasize market-specific promotions. CIM's team-stream inventory is a "
            "natural fit: advertise BetRivers during the Guardians stream to reach Ohio bettors, "
            "during the Tigers stream to reach Michigan bettors.\n\n"
            "Tier 1 classification: $75M spend, 13-market overlap, and the highest-alignment "
            "vertical in CIM's portfolio. Sports betting operators convert at the highest rate "
            "in the pipeline. Prioritize for immediate outreach."
        ),
        "tier": "1",
        "vertical": "Sports Betting & Gaming",
    },
    "d.r. horton": {
        "apollo": {
            "name": "D.R. Horton",
            "industry": "Real Estate",
            "annual_revenue": 125_000_000,
            "estimated_employees": 1200,
            "city": "Arlington",
            "state": "Texas",
        },
        "contacts": [
            {"first_name": "Lisa", "last_name": "Martinez", "title": "Director of Marketing", "email": "lisa.martinez@drhorton.com"},
            {"first_name": "James", "last_name": "Wilson", "title": "VP Advertising", "email": "james.wilson@drhorton.com"},
        ],
        "brief": (
            "D.R. Horton is America's largest homebuilder by volume with an estimated $125M "
            "annual advertising budget. They operate in 33 states and 110 markets, with "
            "significant presence in all 13 CIM priority DMAs. Their advertising is heavily "
            "local — each division runs its own campaigns targeting specific communities.\n\n"
            "Homebuilders are a high-value CTV prospect because their buying cycle is "
            "hyper-local: a family watching the Rays game in Tampa is exactly the audience "
            "for a new D.R. Horton development in Wesley Chapel. CIM's DMA-level targeting "
            "delivers this precision without the waste of a national broadcast buy.\n\n"
            "The RSN disruption is particularly relevant: local sports viewers skew toward "
            "homeowners and the M30-54 demographic that indexes highest for home purchases. "
            "As this audience migrates from linear to streaming, D.R. Horton's local TV "
            "budgets need a new home — CIM provides the same audience on the new platform.\n\n"
            "Tier 1 classification: $125M spend across all 13 CIM markets. Multi-divisional "
            "structure means multiple entry points — regional marketing directors often have "
            "independent media budgets. Approach as a national account with local activation."
        ),
        "tier": "1",
        "vertical": "Real Estate & Home Builders",
    },
}


def get_mock_data(company_name: str) -> dict:
    """Get mock enrichment data for a company name.

    Looks up the company in the mock database. If not found, generates
    a plausible profile based on the company name so ANY company name
    produces a realistic demo result.

    Args:
        company_name: The company name to look up or generate data for.

    Returns:
        Dict with keys: apollo, contacts, brief, tier, vertical
    """
    key = company_name.lower().strip()

    # Check exact match first
    if key in MOCK_COMPANIES:
        return MOCK_COMPANIES[key]

    # Generate a plausible profile for unknown companies
    verticals = [
        "Automotive Dealer Groups", "QSR & Fast-Casual Restaurants",
        "Healthcare Systems & Providers", "Regional Banks & Credit Unions",
        "Retail Chains", "Home Services", "Tourism & Hospitality",
    ]
    vertical = random.choice(verticals)
    revenue = random.choice([15_000_000, 25_000_000, 40_000_000, 65_000_000, 90_000_000])
    tier = "1" if revenue >= 100_000_000 else "2" if revenue >= 40_000_000 else "3" if revenue >= 10_000_000 else "4"

    return {
        "apollo": {
            "name": company_name,
            "industry": vertical.split(" ")[0],
            "annual_revenue": revenue,
            "estimated_employees": random.randint(100, 800),
            "city": random.choice(["Detroit", "Cleveland", "Tampa", "Phoenix", "Atlanta", "Los Angeles"]),
            "state": random.choice(["Michigan", "Ohio", "Florida", "Arizona", "Georgia", "California"]),
        },
        "contacts": [
            {"first_name": "Alex", "last_name": "Johnson", "title": "VP Marketing", "email": f"alex.johnson@{key.replace(' ', '').replace(chr(39), '')}.com"},
            {"first_name": "Morgan", "last_name": "Lee", "title": "Media Director", "email": f"morgan.lee@{key.replace(' ', '').replace(chr(39), '')}.com"},
        ],
        "brief": (
            f"{company_name} represents a strong prospect for Cast Iron Media's sports-specific "
            f"CTV platform. With an estimated ${revenue:,} annual advertising budget in the "
            f"{vertical} vertical, they align well with CIM's target advertiser profile.\n\n"
            f"Their geographic footprint overlaps with multiple CIM priority DMAs where RSN "
            f"disruption is creating new streaming ad inventory. The shift from linear to OTT "
            f"distribution means local sports audiences that previously reached via broadcast "
            f"are now accessible through CIM's Foundry platform with DMA-level precision.\n\n"
            f"Recommended approach: Lead with market-specific case studies showing how similar "
            f"advertisers in the {vertical} vertical have activated across multiple DMAs through "
            f"a single CIM insertion order. Emphasize the 95%+ ad completion rate versus 65% "
            f"on general programmatic — a key differentiator for advertisers migrating from "
            f"guaranteed broadcast delivery.\n\n"
            f"Tier {tier} classification based on estimated spend and market alignment."
        ),
        "tier": tier,
        "vertical": vertical,
    }
