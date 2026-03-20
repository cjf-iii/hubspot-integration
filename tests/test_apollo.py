"""Tests for the Apollo.io API client.

Uses respx to intercept httpx requests so no real network calls are made.
Each test verifies:
  1. The correct endpoint is called with the api_key in the request body.
  2. The response is correctly normalised into the expected output shape.
  3. Edge cases (404, empty results, missing fields) are handled gracefully.

All mock.calls assertions are inside the respx.mock() context — the call
log is reset when the context exits.
"""

import json

import httpx
import pytest
import respx

from cim.apollo import ApolloClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Return an ApolloClient with a test API key and default base URL."""
    c = ApolloClient(api_key="test-apollo-key", base_url="https://api.apollo.io/api/v1")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# enrich_company tests
# ---------------------------------------------------------------------------

def test_enrich_company_returns_normalised_fields(client):
    """enrich_company extracts the expected fields from Apollo's organization dict."""
    apollo_response = {
        "organization": {
            "name": "Acme Broadcasting",
            "industry": "Media & Entertainment",
            "annual_revenue": 5000000,
            "estimated_num_employees": 120,
            "city": "Nashville",
            "state": "Tennessee",
        }
    }

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/organizations/enrich").mock(
            return_value=httpx.Response(200, json=apollo_response)
        )

        result = client.enrich_company("acme.com")

        # Verify the normalised output shape matches what HubSpot enrichment expects
        assert result["name"] == "Acme Broadcasting"
        assert result["industry"] == "Media & Entertainment"
        assert result["annual_revenue"] == 5000000
        assert result["estimated_employees"] == 120
        assert result["city"] == "Nashville"
        assert result["state"] == "Tennessee"

        # Verify the api_key was sent in the request body (Apollo's auth pattern)
        sent = json.loads(mock.calls[0].request.content)
        assert sent["api_key"] == "test-apollo-key"
        assert sent["domain"] == "acme.com"


def test_enrich_company_returns_empty_dict_on_404(client):
    """enrich_company returns {} when Apollo has no record for the domain."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/organizations/enrich").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )

        result = client.enrich_company("unknown-domain.com")

        # Graceful empty return — callers skip enrichment when nothing is found
        assert result == {}


def test_enrich_company_returns_empty_dict_when_organization_missing(client):
    """enrich_company returns {} when the response has no 'organization' key."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/organizations/enrich").mock(
            return_value=httpx.Response(200, json={"organization": None})
        )

        result = client.enrich_company("sparse.com")

        assert result == {}


def test_enrich_company_handles_partial_fields(client):
    """enrich_company returns None for fields Apollo doesn't have data on."""
    apollo_response = {
        "organization": {
            "name": "Minimal Corp",
            # industry, revenue, employees, city, state all absent
        }
    }

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/organizations/enrich").mock(
            return_value=httpx.Response(200, json=apollo_response)
        )

        result = client.enrich_company("minimal.com")

        assert result["name"] == "Minimal Corp"
        # Missing fields should be None, not raise KeyError
        assert result["industry"] is None
        assert result["annual_revenue"] is None
        assert result["estimated_employees"] is None
        assert result["city"] is None
        assert result["state"] is None


# ---------------------------------------------------------------------------
# find_contacts tests
# ---------------------------------------------------------------------------

def test_find_contacts_returns_normalised_people(client):
    """find_contacts extracts first_name, last_name, title, email from Apollo people."""
    apollo_response = {
        "people": [
            {
                "first_name": "Jane",
                "last_name": "Smith",
                "title": "VP Marketing",
                "email": "jane@acme.com",
            },
            {
                "first_name": "Bob",
                "last_name": "Jones",
                "title": "Media Director",
                "email": "bob@acme.com",
            },
        ]
    }

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/mixed_people/search").mock(
            return_value=httpx.Response(200, json=apollo_response)
        )

        results = client.find_contacts("acme.com", limit=3)

        assert len(results) == 2
        assert results[0]["first_name"] == "Jane"
        assert results[0]["last_name"] == "Smith"
        assert results[0]["title"] == "VP Marketing"
        assert results[0]["email"] == "jane@acme.com"

        # Verify api_key, domain, and limit are sent correctly in the request body
        sent = json.loads(mock.calls[0].request.content)
        assert sent["api_key"] == "test-apollo-key"
        assert sent["q_organization_domains"] == "acme.com"
        assert sent["per_page"] == 3
        assert sent["page"] == 1
        # Verify the title filter list is non-empty (we don't assert exact contents
        # to avoid brittleness, but it must be present)
        assert isinstance(sent["person_titles"], list)
        assert len(sent["person_titles"]) > 0


def test_find_contacts_returns_empty_list_when_no_people(client):
    """find_contacts returns [] when Apollo finds no matching contacts."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/mixed_people/search").mock(
            return_value=httpx.Response(200, json={"people": []})
        )

        results = client.find_contacts("nomatches.com")

        assert results == []


def test_find_contacts_handles_missing_people_key(client):
    """find_contacts returns [] when Apollo response has no 'people' key."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/mixed_people/search").mock(
            return_value=httpx.Response(200, json={})
        )

        results = client.find_contacts("nomatches.com")

        assert results == []


def test_find_contacts_respects_limit(client):
    """find_contacts passes the limit value as per_page in the request body."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/mixed_people/search").mock(
            return_value=httpx.Response(200, json={"people": []})
        )

        client.find_contacts("acme.com", limit=5)

        sent = json.loads(mock.calls[0].request.content)
        assert sent["per_page"] == 5


def test_find_contacts_none_email_handled(client):
    """find_contacts includes contacts whose email Apollo hasn't revealed."""
    apollo_response = {
        "people": [
            {
                "first_name": "Alice",
                "last_name": "Chen",
                "title": "CMO",
                # email absent from Apollo response (not unlocked)
            }
        ]
    }

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.apollo.io/api/v1/mixed_people/search").mock(
            return_value=httpx.Response(200, json=apollo_response)
        )

        results = client.find_contacts("acme.com")

        assert len(results) == 1
        assert results[0]["first_name"] == "Alice"
        # email should be None rather than raising KeyError
        assert results[0]["email"] is None
