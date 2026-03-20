"""Tests for the enrichment orchestrator.

Uses unittest.mock to patch HubSpotClient, ApolloClient, and
generate_prospect_brief so no real network calls or API charges are incurred.

Each test verifies:
  1. The correct client methods are called with the expected arguments.
  2. CIM business logic (tier, vertical, domain inference) is correct.
  3. The return dict has the right shape and values.
  4. Edge cases (missing domain, duplicate contacts, sparse Apollo data) are
     handled gracefully without raising.

Convention: _make_mock_* helpers build pre-wired MagicMock objects so the
individual test bodies stay focused on assertions rather than mock setup.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from cim.enrichment import (
    _estimate_tier,
    _infer_domain,
    _map_vertical,
    enrich_company,
)


# ---------------------------------------------------------------------------
# Unit tests for pure helper functions
# ---------------------------------------------------------------------------

class TestEstimateTier:
    """_estimate_tier maps revenue to the correct CIM tier string."""

    def test_none_revenue_returns_tier_4(self):
        """No revenue data defaults to lowest-priority tier."""
        assert _estimate_tier(None) == "4"

    def test_below_10m_returns_tier_4(self):
        assert _estimate_tier(9_999_999) == "4"

    def test_exactly_10m_returns_tier_3(self):
        assert _estimate_tier(10_000_000) == "3"

    def test_between_10m_and_40m_returns_tier_3(self):
        assert _estimate_tier(25_000_000) == "3"

    def test_exactly_40m_returns_tier_2(self):
        assert _estimate_tier(40_000_000) == "2"

    def test_between_40m_and_100m_returns_tier_2(self):
        assert _estimate_tier(75_000_000) == "2"

    def test_exactly_100m_returns_tier_1(self):
        assert _estimate_tier(100_000_000) == "1"

    def test_above_100m_returns_tier_1(self):
        assert _estimate_tier(500_000_000) == "1"


class TestMapVertical:
    """_map_vertical maps Apollo industry strings to CIM verticals."""

    def test_none_returns_other(self):
        assert _map_vertical(None) == "Other"

    def test_empty_string_returns_other(self):
        assert _map_vertical("") == "Other"

    def test_unrecognised_industry_returns_other(self):
        assert _map_vertical("Nuclear Energy") == "Other"

    def test_restaurants_maps_to_qsr(self):
        assert _map_vertical("Restaurants") == "QSR & Fast-Casual Restaurants"

    def test_food_maps_to_qsr(self):
        assert _map_vertical("Food Production") == "QSR & Fast-Casual Restaurants"

    def test_automotive_maps_correctly(self):
        assert _map_vertical("Automotive") == "Automotive Dealer Groups"

    def test_gambling_maps_to_gaming(self):
        assert _map_vertical("Gambling & Casinos") == "Sports Betting & Gaming"

    def test_casino_maps_to_gaming(self):
        assert _map_vertical("Casino") == "Sports Betting & Gaming"

    def test_hospital_maps_to_healthcare(self):
        assert _map_vertical("Hospital & Health Care") == "Healthcare Systems & Providers"

    def test_health_maps_to_healthcare(self):
        assert _map_vertical("Health, Wellness & Fitness") == "Healthcare Systems & Providers"

    def test_insurance_maps_to_legal(self):
        assert _map_vertical("Insurance") == "Personal Injury & Legal Services"

    def test_law_maps_to_legal(self):
        assert _map_vertical("Law Practice") == "Personal Injury & Legal Services"

    def test_banking_maps_to_financial(self):
        assert _map_vertical("Banking") == "Regional Banks & Credit Unions"

    def test_financial_maps_to_financial(self):
        assert _map_vertical("Financial Services") == "Regional Banks & Credit Unions"

    def test_retail_maps_correctly(self):
        assert _map_vertical("Retail") == "Retail Chains"

    def test_hospitality_maps_correctly(self):
        assert _map_vertical("Hospitality") == "Tourism & Hospitality"

    def test_real_estate_maps_correctly(self):
        assert _map_vertical("Real Estate") == "Real Estate & Home Builders"

    def test_construction_maps_to_home_services(self):
        assert _map_vertical("Construction") == "Home Services"

    def test_higher_education_maps_correctly(self):
        assert _map_vertical("Higher Education") == "Higher Education"

    def test_case_insensitive_matching(self):
        """Industry matching is case-insensitive."""
        assert _map_vertical("AUTOMOTIVE") == "Automotive Dealer Groups"
        assert _map_vertical("Automotive") == "Automotive Dealer Groups"


class TestInferDomain:
    """_infer_domain derives a .com domain from a company name."""

    def test_simple_two_word_name(self):
        assert _infer_domain("Acme Corp") == "acmecorp.com"

    def test_apostrophe_removed(self):
        assert _infer_domain("O'Brien's Pub") == "obrienspub.com"

    def test_already_lowercase(self):
        assert _infer_domain("burger king") == "burgerking.com"

    def test_uppercase_lowercased(self):
        assert _infer_domain("Burger King") == "burgerking.com"

    def test_single_word_name(self):
        assert _infer_domain("Walmart") == "walmart.com"

    def test_multiple_spaces(self):
        assert _infer_domain("Best Buy Stores") == "bestbuystores.com"


# ---------------------------------------------------------------------------
# Fixtures and helpers for enrich_company integration tests
# ---------------------------------------------------------------------------

def _make_hubspot_mock(
    company_name: str = "Test Corp",
    domain: str = "testcorp.com",
) -> MagicMock:
    """Build a HubSpotClient mock pre-wired with sensible defaults.

    Returns a MagicMock whose methods return minimal valid HubSpot response
    dicts so enrich_company can run to completion without KeyError.
    """
    mock_hs = MagicMock()

    # get_company returns a properties dict with name and domain
    mock_hs.get_company.return_value = {
        "id": "42",
        "properties": {"name": company_name, "domain": domain},
    }
    # update_company returns the patched company (content not inspected)
    mock_hs.update_company.return_value = {"id": "42"}

    # create_contact must return a dict with "id" so _associate can be called
    mock_hs.create_contact.return_value = {"id": "200"}

    # create_note and create_task return minimal dicts — callers don't use them
    mock_hs.create_note.return_value = {"id": "300"}
    mock_hs.create_task.return_value = {"id": "400"}

    # _associate is called after contact creation and after note/task creation
    mock_hs._associate.return_value = None

    return mock_hs


def _make_apollo_mock(
    annual_revenue: int | None = 50_000_000,
    industry: str = "Automotive",
    contacts: list | None = None,
) -> MagicMock:
    """Build an ApolloClient mock with configurable firmographic data."""
    mock_apollo = MagicMock()

    mock_apollo.enrich_company.return_value = {
        "name": "Test Corp",
        "industry": industry,
        "annual_revenue": annual_revenue,
        "estimated_employees": 500,
        "city": "Detroit",
        "state": "Michigan",
    }

    if contacts is None:
        contacts = [
            {
                "first_name": "Jane",
                "last_name": "Smith",
                "title": "VP Marketing",
                "email": "jane@testcorp.com",
            }
        ]
    mock_apollo.find_contacts.return_value = contacts

    return mock_apollo


# ---------------------------------------------------------------------------
# Full pipeline integration tests
# ---------------------------------------------------------------------------

class TestEnrichCompanyFullFlow:
    """enrich_company orchestrates the full eight-step pipeline correctly."""

    def test_returns_expected_keys(self):
        """enrich_company returns a dict with all required summary keys."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="AI brief text"):
            result = enrich_company(mock_hs, mock_apollo, "key", "42")

        assert set(result.keys()) == {
            "company_id", "company_name", "tier", "vertical",
            "revenue", "contacts_created", "brief_created",
        }

    def test_company_id_and_name_in_result(self):
        """Result carries the input company_id and the name from HubSpot."""
        mock_hs = _make_hubspot_mock(company_name="Acme Auto")
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "99")

        assert result["company_id"] == "99"
        assert result["company_name"] == "Acme Auto"

    def test_tier_derived_from_apollo_revenue(self):
        """Tier is correctly derived from Apollo's annual_revenue figure."""
        mock_hs = _make_hubspot_mock()
        # $75M → Tier 2
        mock_apollo = _make_apollo_mock(annual_revenue=75_000_000)

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        assert result["tier"] == "2"
        assert result["revenue"] == 75_000_000

    def test_vertical_derived_from_apollo_industry(self):
        """Vertical is correctly derived from Apollo's industry string."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock(industry="Automotive")

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        assert result["vertical"] == "Automotive Dealer Groups"

    def test_contacts_created_count_matches(self):
        """contacts_created reflects how many contacts were successfully created."""
        mock_hs = _make_hubspot_mock()
        two_contacts = [
            {"first_name": "A", "last_name": "B", "title": "CMO", "email": "a@b.com"},
            {"first_name": "C", "last_name": "D", "title": "VP", "email": "c@d.com"},
        ]
        mock_apollo = _make_apollo_mock(contacts=two_contacts)

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        assert result["contacts_created"] == 2

    def test_brief_created_is_true_on_success(self):
        """brief_created is True when the note is created without error."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief text"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        assert result["brief_created"] is True


# ---------------------------------------------------------------------------
# Client method call verification tests
# ---------------------------------------------------------------------------

class TestEnrichCompanyClientCalls:
    """Verify each client method is called with the correct arguments."""

    def test_get_company_called_with_correct_id_and_properties(self):
        """get_company is called once with the right company_id and property list."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "42")

        mock_hs.get_company.assert_called_once_with(
            "42", properties=["name", "domain"]
        )

    def test_apollo_enrich_called_with_domain(self):
        """apollo.enrich_company is called with the HubSpot domain."""
        mock_hs = _make_hubspot_mock(domain="acme.com")
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "1")

        mock_apollo.enrich_company.assert_called_once_with("acme.com")

    def test_apollo_find_contacts_called_with_domain(self):
        """apollo.find_contacts is called with the same domain as enrich_company."""
        mock_hs = _make_hubspot_mock(domain="acme.com")
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "1")

        mock_apollo.find_contacts.assert_called_once_with("acme.com")

    def test_generate_prospect_brief_called_with_correct_args(self):
        """generate_prospect_brief receives api_key, name, apollo_data, and contacts."""
        mock_hs = _make_hubspot_mock(company_name="SportsBet Inc")
        apollo_data = {
            "name": "SportsBet Inc",
            "industry": "Gambling",
            "annual_revenue": 80_000_000,
            "estimated_employees": 200,
            "city": "Las Vegas",
            "state": "Nevada",
        }
        contacts = [{"first_name": "X", "last_name": "Y", "title": "CMO", "email": "x@y.com"}]
        mock_apollo = MagicMock()
        mock_apollo.enrich_company.return_value = apollo_data
        mock_apollo.find_contacts.return_value = contacts

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief") as mock_brief:
            enrich_company(mock_hs, mock_apollo, "my-api-key", "5")

        mock_brief.assert_called_once_with(
            api_key="my-api-key",
            company_name="SportsBet Inc",
            company_data=apollo_data,
            contacts=contacts,
        )

    def test_update_company_called_with_tier_and_vertical(self):
        """update_company patches the company with cim_tier and cim_vertical."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock(annual_revenue=50_000_000, industry="Automotive")

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "42")

        # Verify the first positional arg is the company_id
        call_args = mock_hs.update_company.call_args
        assert call_args.args[0] == "42"
        props = call_args.args[1]
        assert props["cim_tier"] == "2"           # $50M → Tier 2
        assert props["cim_vertical"] == "Automotive Dealer Groups"

    def test_create_contact_called_for_each_apollo_contact(self):
        """create_contact is called once per contact returned by Apollo."""
        mock_hs = _make_hubspot_mock()
        two_contacts = [
            {"first_name": "A", "last_name": "B", "title": "CMO", "email": "a@test.com"},
            {"first_name": "C", "last_name": "D", "title": "VP",  "email": "c@test.com"},
        ]
        mock_apollo = _make_apollo_mock(contacts=two_contacts)

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "1")

        assert mock_hs.create_contact.call_count == 2

    def test_create_note_called_with_company_id(self):
        """create_note is called once with the company_id for association."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="My brief"):
            enrich_company(mock_hs, mock_apollo, "key", "42")

        mock_hs.create_note.assert_called_once()
        call_kwargs = mock_hs.create_note.call_args
        # Second positional arg or keyword arg should be the company_id
        assert call_kwargs.kwargs.get("company_id") == "42" or call_kwargs.args[1] == "42"

    def test_note_body_contains_ai_brief(self):
        """The note body HTML contains the text returned by generate_prospect_brief."""
        mock_hs = _make_hubspot_mock(company_name="Test Corp")
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Custom brief content"):
            enrich_company(mock_hs, mock_apollo, "key", "1")

        note_body = mock_hs.create_note.call_args.args[0]
        assert "Custom brief content" in note_body
        assert "AI Prospect Brief" in note_body

    def test_create_task_called_with_company_id(self):
        """create_task is called once with the company_id for association."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "42")

        mock_hs.create_task.assert_called_once()
        call_kwargs = mock_hs.create_task.call_args
        assert call_kwargs.kwargs.get("company_id") == "42" or call_kwargs.args[2] == "42"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEnrichCompanyEdgeCases:
    """Edge cases: missing domain, duplicate contacts, empty Apollo data."""

    def test_infers_domain_when_hubspot_has_none(self):
        """Apollo is called with an inferred domain when HubSpot has no domain."""
        mock_hs = MagicMock()
        # HubSpot returns company with no domain set
        mock_hs.get_company.return_value = {
            "id": "1",
            "properties": {"name": "Burger King", "domain": None},
        }
        mock_hs.update_company.return_value = {"id": "1"}
        mock_hs.create_contact.return_value = {"id": "2"}
        mock_hs.create_note.return_value = {"id": "3"}
        mock_hs.create_task.return_value = {"id": "4"}

        mock_apollo = _make_apollo_mock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            enrich_company(mock_hs, mock_apollo, "key", "1")

        # Apollo should be called with the inferred domain, not None
        mock_apollo.enrich_company.assert_called_once_with("burgerking.com")
        mock_apollo.find_contacts.assert_called_once_with("burgerking.com")

    def test_duplicate_contact_error_is_swallowed(self):
        """contacts_created is 0 (not an exception) when all contacts are duplicates."""
        mock_hs = _make_hubspot_mock()
        # create_contact raises on every call (simulates 409 Conflict)
        mock_hs.create_contact.side_effect = Exception("409 Conflict")
        mock_apollo = _make_apollo_mock(contacts=[
            {"first_name": "X", "last_name": "Y", "title": "CMO", "email": "x@y.com"}
        ])

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        # Pipeline completes, contacts_created reflects the actual count (0)
        assert result["contacts_created"] == 0
        # The note and task should still be created even after contact failure
        mock_hs.create_note.assert_called_once()
        mock_hs.create_task.assert_called_once()

    def test_partial_contact_failure_counts_successes(self):
        """contacts_created only counts the successfully created contacts."""
        mock_hs = _make_hubspot_mock()
        # First call succeeds, second raises (duplicate)
        mock_hs.create_contact.side_effect = [
            {"id": "100"},  # success
            Exception("409 Conflict"),  # duplicate
        ]
        two_contacts = [
            {"first_name": "A", "last_name": "B", "title": "CMO", "email": "a@b.com"},
            {"first_name": "C", "last_name": "D", "title": "VP",  "email": "c@d.com"},
        ]
        mock_apollo = _make_apollo_mock(contacts=two_contacts)

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        assert result["contacts_created"] == 1

    def test_empty_apollo_data_produces_tier_4_other(self):
        """Empty Apollo data results in Tier 4 and 'Other' vertical."""
        mock_hs = _make_hubspot_mock()
        mock_apollo = MagicMock()
        # Apollo has no record for this domain
        mock_apollo.enrich_company.return_value = {}
        mock_apollo.find_contacts.return_value = []
        mock_hs.update_company.return_value = {"id": "1"}
        mock_hs.create_note.return_value = {"id": "2"}
        mock_hs.create_task.return_value = {"id": "3"}

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        assert result["tier"] == "4"
        assert result["vertical"] == "Other"
        assert result["revenue"] is None
        assert result["contacts_created"] == 0

    def test_no_domain_and_no_name_skips_apollo(self):
        """Apollo is not called when both domain and company name are absent."""
        mock_hs = MagicMock()
        mock_hs.get_company.return_value = {
            "id": "1",
            "properties": {"name": "", "domain": ""},
        }
        mock_hs.update_company.return_value = {"id": "1"}
        mock_hs.create_note.return_value = {"id": "2"}
        mock_hs.create_task.return_value = {"id": "3"}

        mock_apollo = MagicMock()

        with patch("cim.enrichment.generate_prospect_brief", return_value="Brief"):
            result = enrich_company(mock_hs, mock_apollo, "key", "1")

        # No domain could be derived, so Apollo should never be called
        mock_apollo.enrich_company.assert_not_called()
        mock_apollo.find_contacts.assert_not_called()
        assert result["tier"] == "4"
