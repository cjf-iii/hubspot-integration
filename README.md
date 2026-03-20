# HubSpot Integration

AI-powered prospect enrichment engine for sports CTV ad sales. Takes a company name, enriches it with market data and AI-generated briefs, and writes everything back to HubSpot CRM.

## How It Works

1. Add a company name to HubSpot
2. Engine queries Apollo.io for company data and key contacts
3. Claude AI generates a prospect brief with CIM-specific context
4. Enriched data writes back to HubSpot: custom properties, contacts, AI brief note, review task

## Architecture

```
Company Name
    ↓
Apollo.io → Company data + Contacts
    ↓
Claude AI → Prospect Brief (200-300 words)
    ↓
HubSpot API → Properties + Contacts + Note + Task
    ↓
Enriched Record (10 seconds)
```

## Prerequisites

- Python 3.11+
- HubSpot account with API key (free tier works)
- Anthropic API key
- Apollo.io API key

## Installation

```bash
git clone https://github.com/cjf-iii/hubspot-integration.git
cd hubspot-integration
pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your API keys
```

## Usage

### Setup — Configure HubSpot with CIM properties

```bash
cim setup
```

### Enrich — Enrich a specific company

```bash
cim enrich --name "Culver's"
cim enrich --id 12345678
```

### Demo — Full demo flow (create + enrich + display)

```bash
cim demo "Culver's"
```

## What Gets Created in HubSpot

### Company Properties

- **CIM Tier** (1-4 priority scoring)
- **Sports Alignment Score** (1-10)
- **CIM Vertical** (industry category)

### Deal Properties

- **IO Status** (Draft/Sent/Signed/Active/Completed)
- **Campaign Type** (CTV Programmatic/Sponsorship/Custom)
- **CPM Rate, Impressions Committed**

### On Each Enriched Company

- All properties populated from Apollo.io data
- 2-3 decision maker contacts with titles and emails
- AI Prospect Brief (Note on company timeline)
- Review task (in seller's task queue)

## Running Tests

```bash
pytest tests/ -v
```

## Visual Aid

Open `visual/enrichment-demo.html` in a browser to see the before/after enrichment transformation.

## License

MIT
