"""Tests for the HubSpot CRM API client.

Uses respx to intercept httpx requests so no real network calls are made.
Each test verifies:
  1. The correct HTTP method and endpoint URL is called.
  2. The request payload contains the expected structure.
  3. The method returns the correct parsed response.

IMPORTANT: All assertions on mock.calls must be made *inside* the respx.mock()
context manager block — respx resets the call log when the context exits.
"""

import json

import httpx
import pytest
import respx

from cim.hubspot import HubSpotClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Return a HubSpotClient pointed at the standard base URL.

    The underlying httpx.Client is intercepted by respx.mock() context
    managers in each individual test.
    """
    c = HubSpotClient(api_key="test-key", base_url="https://api.hubapi.com")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Company tests
# ---------------------------------------------------------------------------

def test_create_company(client):
    """create_company POSTs to /crm/v3/objects/companies and returns the response."""
    expected_response = {"id": "123", "properties": {"name": "Acme Corp"}}

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.hubapi.com/crm/v3/objects/companies").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        result = client.create_company({"name": "Acme Corp", "domain": "acme.com"})

        # All mock.calls assertions must be inside the context — respx resets on exit
        assert result == expected_response
        sent = json.loads(mock.calls[0].request.content)
        assert sent["properties"]["name"] == "Acme Corp"
        assert sent["properties"]["domain"] == "acme.com"


def test_update_company(client):
    """update_company PATCHes /crm/v3/objects/companies/{id} and returns response."""
    company_id = "456"
    expected_response = {"id": company_id, "properties": {"name": "Updated Corp"}}

    with respx.mock(assert_all_called=True) as mock:
        mock.patch(
            f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
        ).mock(return_value=httpx.Response(200, json=expected_response))

        result = client.update_company(company_id, {"name": "Updated Corp"})

        assert result == expected_response
        sent = json.loads(mock.calls[0].request.content)
        assert sent["properties"]["name"] == "Updated Corp"


# ---------------------------------------------------------------------------
# Note tests
# ---------------------------------------------------------------------------

def test_create_note_without_company(client):
    """create_note POSTs to /crm/v3/objects/notes and returns the note."""
    expected_response = {"id": "789", "properties": {"hs_note_body": "Hello"}}

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.hubapi.com/crm/v3/objects/notes").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        result = client.create_note("Hello")

        assert result == expected_response
        sent = json.loads(mock.calls[0].request.content)
        # Verify required HubSpot note fields are present
        assert sent["properties"]["hs_note_body"] == "Hello"
        assert "hs_timestamp" in sent["properties"]
        # hs_timestamp should be a numeric string (epoch ms)
        assert sent["properties"]["hs_timestamp"].isdigit()


def test_create_note_with_company_associates(client):
    """create_note with company_id calls the v4 associations endpoint after creation."""
    note_response = {"id": "100", "properties": {}}

    with respx.mock(assert_all_called=True) as mock:
        # Mock note creation endpoint
        mock.post("https://api.hubapi.com/crm/v3/objects/notes").mock(
            return_value=httpx.Response(200, json=note_response)
        )
        # Mock the v4 association PUT call linking note 100 to company 999
        mock.put(
            "https://api.hubapi.com/crm/v4/objects/notes/100/associations/companies/999"
        ).mock(return_value=httpx.Response(200, json={}))

        result = client.create_note("Note body", company_id="999")

        assert result == note_response
        # Two calls should have been made: create note + create association
        assert len(mock.calls) == 2


# ---------------------------------------------------------------------------
# Contact tests
# ---------------------------------------------------------------------------

def test_create_contact(client):
    """create_contact POSTs to /crm/v3/objects/contacts and returns response."""
    expected_response = {"id": "200", "properties": {"email": "jane@acme.com"}}

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.hubapi.com/crm/v3/objects/contacts").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        result = client.create_contact(
            {"firstname": "Jane", "lastname": "Doe", "email": "jane@acme.com"}
        )

        assert result == expected_response
        sent = json.loads(mock.calls[0].request.content)
        assert sent["properties"]["email"] == "jane@acme.com"
        assert sent["properties"]["firstname"] == "Jane"


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------

def test_create_task_without_company(client):
    """create_task POSTs to /crm/v3/objects/tasks with correct default properties."""
    expected_response = {"id": "300", "properties": {"hs_task_subject": "Follow up"}}

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.hubapi.com/crm/v3/objects/tasks").mock(
            return_value=httpx.Response(200, json=expected_response)
        )

        result = client.create_task("Follow up", body="Call the prospect")

        assert result == expected_response
        sent = json.loads(mock.calls[0].request.content)
        props = sent["properties"]
        # Verify all required task fields are present and correct
        assert props["hs_task_subject"] == "Follow up"
        assert props["hs_task_body"] == "Call the prospect"
        assert props["hs_task_status"] == "NOT_STARTED"
        assert props["hs_task_priority"] == "HIGH"
        assert "hs_timestamp" in props


def test_create_task_with_company_associates(client):
    """create_task with company_id calls the v4 associations endpoint after creation."""
    task_response = {"id": "301", "properties": {}}

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.hubapi.com/crm/v3/objects/tasks").mock(
            return_value=httpx.Response(200, json=task_response)
        )
        mock.put(
            "https://api.hubapi.com/crm/v4/objects/tasks/301/associations/companies/888"
        ).mock(return_value=httpx.Response(200, json={}))

        result = client.create_task("Follow up", company_id="888")

        assert result == task_response
        # Verify both the task creation and association calls were made
        assert len(mock.calls) == 2


# ---------------------------------------------------------------------------
# Property management tests
# ---------------------------------------------------------------------------

def test_create_properties(client):
    """create_properties POSTs to the batch create endpoint and returns response."""
    definitions = [
        {
            "name": "cim_vertical",
            "label": "CIM Vertical",
            "type": "string",
            "fieldType": "text",
            "groupName": "cim_enrichment",
        }
    ]
    expected_response = {"status": "COMPLETE", "results": [{"name": "cim_vertical"}]}

    with respx.mock(assert_all_called=True) as mock:
        mock.post(
            "https://api.hubapi.com/crm/v3/properties/companies/batch/create"
        ).mock(return_value=httpx.Response(200, json=expected_response))

        result = client.create_properties("companies", definitions)

        assert result == expected_response
        sent = json.loads(mock.calls[0].request.content)
        # Batch create endpoint expects an "inputs" array wrapper
        assert sent["inputs"] == definitions


def test_create_property_group_409_is_ok(client):
    """create_property_group treats 409 Conflict as idempotent success."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post(
            "https://api.hubapi.com/crm/v3/properties/companies/groups"
        ).mock(return_value=httpx.Response(409, json={"message": "already exists"}))

        # Should not raise — 409 is expected when the group already exists
        result = client.create_property_group(
            "companies", "cim_enrichment", "CIM Enrichment"
        )

        assert result == {}


def test_create_property_group_success(client):
    """create_property_group returns the group dict on 200 success."""
    expected_response = {"name": "cim_enrichment", "label": "CIM Enrichment"}

    with respx.mock(assert_all_called=True) as mock:
        mock.post(
            "https://api.hubapi.com/crm/v3/properties/companies/groups"
        ).mock(return_value=httpx.Response(200, json=expected_response))

        result = client.create_property_group(
            "companies", "cim_enrichment", "CIM Enrichment"
        )

        assert result == expected_response
