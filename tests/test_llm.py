"""Tests for the LLM prospect brief generator.

Uses unittest.mock to patch the Anthropic SDK so no real API calls are made.
Each test verifies:
  1. The function returns a non-empty string.
  2. The prompt sent to Claude contains company-specific data.
  3. Edge cases (missing fields, empty contacts) are handled gracefully.

We patch anthropic.Anthropic at the module level where it is imported
(cim.llm.anthropic.Anthropic) so the mock intercepts the constructor call
inside generate_prospect_brief.
"""

from unittest.mock import MagicMock, patch

import pytest

from cim.llm import generate_prospect_brief


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_anthropic(brief_text: str) -> MagicMock:
    """Build a MagicMock that mimics anthropic.Anthropic well enough for tests.

    Constructs the nested mock chain:
      Anthropic(api_key=...) -> instance
      instance.messages.create(...) -> Message
      message.content[0].text -> brief_text

    This mirrors how generate_prospect_brief uses the SDK so the mock
    transparently replaces the real client without changing production code.
    """
    # Fake TextBlock with a .text attribute
    mock_text_block = MagicMock()
    mock_text_block.text = brief_text

    # Fake Message with .content[0] returning the text block
    mock_message = MagicMock()
    mock_message.content = [mock_text_block]

    # Fake messages namespace with .create() returning the message
    mock_messages = MagicMock()
    mock_messages.create.return_value = mock_message

    # Fake Anthropic client instance
    mock_client = MagicMock()
    mock_client.messages = mock_messages

    # Fake Anthropic class whose constructor returns the mock client
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    return mock_anthropic_cls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_non_empty_string():
    """generate_prospect_brief returns the brief text string from Claude."""
    expected_brief = (
        "Acme Broadcasting is a mid-size media company based in Nashville, Tennessee. "
        "They operate in the Media & Entertainment vertical with strong local DMA presence. "
        "Recommended Tier 2 prospect."
    )
    mock_cls = _make_mock_anthropic(expected_brief)

    company_data = {
        "industry": "Media & Entertainment",
        "annual_revenue": 5_000_000,
        "estimated_employees": 120,
        "city": "Nashville",
        "state": "Tennessee",
    }
    contacts = [
        {"first_name": "Jane", "last_name": "Smith", "title": "VP Marketing", "email": "jane@acme.com"},
    ]

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        result = generate_prospect_brief(
            api_key="test-key",
            company_name="Acme Broadcasting",
            company_data=company_data,
            contacts=contacts,
        )

    assert isinstance(result, str)
    assert len(result) > 0
    assert result == expected_brief


def test_prompt_contains_company_name():
    """The prompt sent to Claude includes the company name."""
    mock_cls = _make_mock_anthropic("Some brief.")

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        generate_prospect_brief(
            api_key="test-key",
            company_name="SportsBet Inc",
            company_data={"industry": "Gambling", "city": "Las Vegas", "state": "Nevada"},
            contacts=[],
        )

    # Retrieve what was passed to messages.create
    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args

    # The user message content should mention the company name
    messages_arg = call_kwargs.kwargs.get("messages") or call_kwargs.args[0] if call_kwargs.args else []
    user_content = next(
        m["content"] for m in call_kwargs.kwargs["messages"] if m["role"] == "user"
    )
    assert "SportsBet Inc" in user_content


def test_prompt_contains_industry_and_location():
    """The prompt includes industry and location from company_data."""
    mock_cls = _make_mock_anthropic("Brief with industry data.")

    company_data = {
        "industry": "Automotive",
        "annual_revenue": 20_000_000,
        "estimated_employees": 350,
        "city": "Detroit",
        "state": "Michigan",
    }

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        generate_prospect_brief(
            api_key="test-key",
            company_name="Detroit Auto Group",
            company_data=company_data,
            contacts=[],
        )

    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args
    user_content = next(
        m["content"] for m in call_kwargs.kwargs["messages"] if m["role"] == "user"
    )

    # All key firmographic fields should appear in the prompt
    assert "Automotive" in user_content
    assert "Detroit" in user_content
    assert "Michigan" in user_content
    assert "20,000,000" in user_content


def test_prompt_contains_contact_names():
    """The prompt includes contact names and titles when contacts are provided."""
    mock_cls = _make_mock_anthropic("Brief with contacts.")

    contacts = [
        {"first_name": "Bob", "last_name": "Jones", "title": "Media Director", "email": "bob@co.com"},
        {"first_name": "Alice", "last_name": "Chen", "title": "CMO", "email": None},
    ]

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        generate_prospect_brief(
            api_key="test-key",
            company_name="Test Co",
            company_data={"industry": "Retail", "city": "Chicago", "state": "Illinois"},
            contacts=contacts,
        )

    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args
    user_content = next(
        m["content"] for m in call_kwargs.kwargs["messages"] if m["role"] == "user"
    )

    assert "Bob" in user_content
    assert "Jones" in user_content
    assert "Media Director" in user_content
    assert "Alice" in user_content
    assert "CMO" in user_content


def test_handles_empty_contacts_gracefully():
    """generate_prospect_brief works without raising when contacts list is empty."""
    mock_cls = _make_mock_anthropic("Brief with no contacts.")

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        result = generate_prospect_brief(
            api_key="test-key",
            company_name="Lonely Corp",
            company_data={"industry": "Healthcare", "city": "Austin", "state": "Texas"},
            contacts=[],
        )

    assert isinstance(result, str)
    assert len(result) > 0

    # Verify the prompt still mentions the no-contacts fallback
    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args
    user_content = next(
        m["content"] for m in call_kwargs.kwargs["messages"] if m["role"] == "user"
    )
    assert "No contacts found" in user_content


def test_handles_missing_company_data_fields():
    """generate_prospect_brief handles None/missing fields without raising."""
    mock_cls = _make_mock_anthropic("Brief with sparse data.")

    # Entirely empty company_data — all fields missing
    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        result = generate_prospect_brief(
            api_key="test-key",
            company_name="Mystery Corp",
            company_data={},
            contacts=[],
        )

    assert isinstance(result, str)
    assert len(result) > 0

    # Verify fallback strings appear in prompt rather than "None" literals
    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args
    user_content = next(
        m["content"] for m in call_kwargs.kwargs["messages"] if m["role"] == "user"
    )
    assert "None" not in user_content
    assert "Unknown" in user_content


def test_api_key_passed_to_anthropic_constructor():
    """generate_prospect_brief passes the api_key to the Anthropic constructor."""
    mock_cls = _make_mock_anthropic("Brief.")

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        generate_prospect_brief(
            api_key="secret-key-xyz",
            company_name="Test Corp",
            company_data={},
            contacts=[],
        )

    # The Anthropic class should have been instantiated with our key
    mock_cls.assert_called_once_with(api_key="secret-key-xyz")


def test_correct_model_used():
    """generate_prospect_brief calls messages.create with the expected model."""
    from cim.llm import _MODEL

    mock_cls = _make_mock_anthropic("Brief.")

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        generate_prospect_brief(
            api_key="test-key",
            company_name="Test Corp",
            company_data={},
            contacts=[],
        )

    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args
    assert call_kwargs.kwargs["model"] == _MODEL


def test_system_prompt_contains_cim_context():
    """The system prompt sent to Claude contains CIM-specific domain context."""
    mock_cls = _make_mock_anthropic("Brief.")

    with patch("cim.llm.anthropic.Anthropic", mock_cls):
        generate_prospect_brief(
            api_key="test-key",
            company_name="Test Corp",
            company_data={},
            contacts=[],
        )

    mock_instance = mock_cls.return_value
    call_kwargs = mock_instance.messages.create.call_args
    system_prompt = call_kwargs.kwargs.get("system", "")

    # The system prompt must reference CIM's core business context
    assert "Cast Iron Media" in system_prompt or "CIM" in system_prompt
    assert "CTV" in system_prompt or "OTT" in system_prompt
    # Must include vertical context so the LLM can reason about alignment
    assert "Sports Betting" in system_prompt or "Auto" in system_prompt
