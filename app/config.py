"""Application configuration settings.

This module defines the ``Settings`` class using ``pydantic-settings`` to
load configuration from environment variables. It centralises all
runtime configuration for the application, such as Google API credentials,
refresh intervals and default filters.
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration values loaded from environment variables.

    Environment variable names map to fields by alias. See the field
    definitions for documentation. All values are optional except for
    the Google credentials and impersonation user; sensible defaults
    are provided for other fields.
    """

    # Google authentication
    google_service_account_json: str = Field(..., alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    google_impersonate_user: str = Field(..., alias="GOOGLE_IMPERSONATE_USER")

    # Directory API configuration
    google_customer: str = Field(
        default="my_customer",
        alias="GOOGLE_CUSTOMER",
        description="Customer ID for Directory API queries. 'my_customer' works for most domains.",
    )

    # Signage behaviour
    refresh_seconds: int = Field(
        default=60,
        alias="REFRESH_SECONDS",
        description=(
            "Interval (in seconds) between free/busy polls. "
            "Minimum 30 is recommended on a Raspberry Pi 4 Model B (8 GB) "
            "to avoid API throttling."
        ),
    )
    soon_minutes: int = Field(
        default=10,
        alias="SOON_MINUTES",
        description="Number of minutes before a meeting when a room is considered 'booked soon'.",
    )

    # UI defaults
    default_building_id: str = Field(
        default="",
        alias="DEFAULT_BUILDING_ID",
        description="Optional default building ID to auto‑filter the UI for shared screens.",
    )

    class Config:
        extra = "ignore"


# Instantiate settings at module import time. This allows other modules to
# import ``settings`` directly without repeatedly reading environment variables.
settings = Settings()