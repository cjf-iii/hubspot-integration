"""Configuration loading from environment variables.

Reads API keys and settings from .env file or environment.
All keys are required — missing keys raise clear error messages.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment.

    frozen=True makes instances immutable and hashable, preventing accidental
    mutation of config values after startup. All fields are set once at load time.
    """
    # Required API credentials — no defaults, must be set in environment
    hubspot_api_key: str
    anthropic_api_key: str
    apollo_api_key: str

    # Base URLs with sensible defaults; override via env if pointing at a sandbox
    hubspot_base_url: str = "https://api.hubapi.com"
    apollo_base_url: str = "https://api.apollo.io/api/v1"


def load_config() -> Config:
    """Load configuration from .env file and environment variables.

    Calls load_dotenv() first so a local .env file populates os.environ,
    then checks that all required keys are present before constructing Config.
    Raises ValueError with a clear message if any required key is missing,
    listing all absent keys at once so the user can fix everything in one pass.
    """
    # Populate os.environ from .env if it exists; no-op if the file is absent
    load_dotenv()

    # Collect every missing required key before raising so the error message
    # tells the user everything they need to fix in a single run.
    missing = []
    for key in ("HUBSPOT_API_KEY", "ANTHROPIC_API_KEY", "APOLLO_API_KEY"):
        if not os.getenv(key):
            missing.append(key)

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in your API keys."
        )

    return Config(
        hubspot_api_key=os.environ["HUBSPOT_API_KEY"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        apollo_api_key=os.environ["APOLLO_API_KEY"],
    )
