"""Apollo.io REST API client for company enrichment and contact discovery.

Wraps two Apollo endpoints:
  - /organizations/enrich  — returns firmographic data for a domain
  - /mixed_people/search   — returns people matching domain + title filters

Apollo uses body-based authentication: the api_key is sent as a field in
the JSON request body rather than as a header. This is Apollo's v1 pattern.

The client is synchronous and uses a shared httpx.Client for connection
reuse across multiple calls in the same enrichment run.
"""

import httpx


# Titles used when searching for relevant contacts at a prospect company.
# Focused on marketing, media buying, and advertising decision-makers —
# the roles most likely to have CTV/OTT ad budget authority at a prospect.
_MARKETING_TITLES = [
    "Chief Marketing Officer",
    "VP Marketing",
    "VP of Marketing",
    "Director of Marketing",
    "Marketing Director",
    "Media Director",
    "Director of Media",
    "VP Media",
    "Media Buyer",
    "Programmatic Director",
    "Director of Advertising",
    "Advertising Manager",
    "Digital Marketing Director",
    "Brand Manager",
]


class ApolloClient:
    """Synchronous Apollo.io API client.

    Handles company enrichment lookups and contact searches against the
    Apollo.io v1 REST API. Authentication is body-based (api_key in JSON),
    so no Authorization header is needed.

    Args:
        api_key:  Apollo.io API key. Sent in request body, not headers.
        base_url: API root, defaults to https://api.apollo.io/api/v1.
                  Override in tests to avoid real network calls.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.apollo.io/api/v1",
    ) -> None:
        # Store key and base separately — key is injected per-request
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

        # Single shared httpx.Client. No auth headers needed — Apollo uses
        # body-based auth so we just need a plain client with a reasonable timeout.
        self._client = httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich_company(self, domain: str) -> dict:
        """Fetch firmographic data for a company by domain.

        Calls Apollo's /organizations/enrich endpoint which returns details
        like industry, revenue range, headcount, and location for a given
        domain. Returns an empty dict if Apollo has no data for the domain
        (404 or missing organization key) so callers can treat missing data
        as a graceful no-op rather than an exception.

        Args:
            domain: The company's primary web domain (e.g. "acme.com").
                    Do not include "https://" or trailing slashes.

        Returns:
            Dict with keys: name, industry, annual_revenue,
            estimated_employees, city, state. Any missing fields from
            Apollo's response are returned as None. Returns {} if Apollo
            has no record for the domain.

        Raises:
            httpx.HTTPStatusError: On unexpected API errors (not 404).
        """
        url = f"{self._base_url}/organizations/enrich"
        # Apollo body-auth: api_key goes in the POST body alongside params
        payload = {"api_key": self._api_key, "domain": domain}
        resp = self._client.post(url, json=payload)

        # 404 means Apollo has no record for this domain — treat as empty
        if resp.status_code == 404:
            return {}

        resp.raise_for_status()
        data = resp.json()

        # Apollo wraps the result in an "organization" key; absent means not found
        org = data.get("organization")
        if not org:
            return {}

        # Extract and normalise the fields CIM cares about for enrichment.
        # All fields can be None if Apollo doesn't have them.
        return {
            "name": org.get("name"),
            "industry": org.get("industry"),
            "annual_revenue": org.get("annual_revenue"),
            "estimated_employees": org.get("estimated_num_employees"),
            "city": org.get("city"),
            "state": org.get("state"),
        }

    def find_contacts(self, domain: str, limit: int = 3) -> list[dict]:
        """Search for marketing/media contacts at a company by domain.

        Uses Apollo's /mixed_people/search endpoint with a curated list of
        marketing and media buying job titles. Filters by organisation domain
        to return people who work at the target company. Results are limited
        to `limit` contacts (default 3) to keep enrichment focused.

        Args:
            domain: The company's primary web domain (e.g. "acme.com").
            limit:  Maximum number of contacts to return (default 3).

        Returns:
            List of dicts with keys: first_name, last_name, title, email.
            email may be None if Apollo hasn't revealed it. Returns [] if
            Apollo finds no matching contacts.

        Raises:
            httpx.HTTPStatusError: On API error.
        """
        url = f"{self._base_url}/mixed_people/search"
        # Apollo body-auth pattern: api_key + search params all in the POST body
        payload = {
            "api_key": self._api_key,
            "q_organization_domains": domain,
            "person_titles": _MARKETING_TITLES,
            "page": 1,
            "per_page": limit,
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Apollo returns results under "people" key; absent means no matches
        people = data.get("people", [])

        # Normalise to the fields CIM needs for HubSpot contact creation
        return [
            {
                "first_name": p.get("first_name"),
                "last_name": p.get("last_name"),
                "title": p.get("title"),
                "email": p.get("email"),
            }
            for p in people
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying httpx client and release connections."""
        self._client.close()

    def __enter__(self) -> "ApolloClient":
        """Support use as a context manager: `with ApolloClient(...) as apollo:`."""
        return self

    def __exit__(self, *_: object) -> None:
        """Ensure close() is called when leaving a with-block."""
        self.close()
