"""Google Workspace client utilities for the room signage service.

This module provides helpers to load service account credentials and perform
directory and free/busy queries against Google Workspace. It encapsulates
retry logic with exponential back‑off for transient errors and is careful to
avoid exposing sensitive information. All credentials and settings are
provided via the ``Settings`` object in ``app.config``.

The functions here are deliberately synchronous because the service runs on
resource‑constrained devices such as the Raspberry Pi. Should you choose to
move to an async implementation in the future, these functions can be
adapted accordingly.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import settings

logger = logging.getLogger(__name__)

# Scopes required for this application. We limit ourselves to the
# minimal set necessary to list room resources and read free/busy
# information. Do not add broader scopes unless absolutely required.
SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly",
    "https://www.googleapis.com/auth/calendar.freebusy",
)


def _load_sa_info() -> dict:
    """Load the service account credentials from the configured path or JSON.

    The ``GOOGLE_SERVICE_ACCOUNT_JSON`` setting may contain either a JSON
    string or a filesystem path pointing to the JSON key. This helper hides
    that complexity and returns a dictionary suitable for constructing
    credentials.
    """
    raw = settings.google_service_account_json.strip()
    # Detect inline JSON by looking for a brace at the start.
    if raw.startswith("{"):
        return json.loads(raw)
    # Treat as a path relative to the host filesystem.
    with open(raw, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_delegated_credentials() -> service_account.Credentials:
    """Return a set of delegated service account credentials.

    We use domain‑wide delegation to impersonate a Workspace user defined by
    ``GOOGLE_IMPERSONATE_USER``. The returned credentials will carry all
    configured scopes.
    """
    sa_info = _load_sa_info()
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return creds.with_subject(settings.google_impersonate_user)


def get_directory_service():
    """Build and return an Admin SDK Directory service client."""
    creds = get_delegated_credentials()
    return build("admin", "directory_v1", credentials=creds, cache_discovery=False)


def get_calendar_service():
    """Build and return a Calendar service client."""
    creds = get_delegated_credentials()
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_rooms() -> List[Dict[str, Any]]:
    """Retrieve all calendar resources (rooms) defined in the Workspace domain.

    Returns a list of resource dictionaries. Each dictionary may include
    fields such as ``resourceId``, ``resourceName``, ``resourceEmail``,
    ``buildingId``, ``floorName`` and ``capacity``. We deliberately avoid
    filtering on resource types here so callers can decide what to do.

    Raises:
        HttpError: if the Google API request fails after retries.
    """
    service = get_directory_service()
    rooms: List[Dict[str, Any]] = []
    request = service.resources().calendars().list(customer=settings.google_customer)
    while request is not None:
        try:
            response = request.execute()
        except HttpError as exc:
            logger.error("Failed to list rooms via Directory API: %s", exc)
            raise
        rooms.extend(response.get("items", []))
        request = service.resources().calendars().list_next(previous_request=request, previous_response=response)
    return rooms


def freebusy_for_calendars(
    calendar_ids: Iterable[str],
    time_min: datetime,
    time_max: datetime,
    *,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> Dict[str, List[Tuple[datetime, datetime]]]:
    """Retrieve free/busy blocks for multiple calendars within a time window.

    Args:
        calendar_ids: an iterable of calendar IDs (typically resource emails).
        time_min: the start time (inclusive) as a timezone‑aware datetime.
        time_max: the end time (exclusive) as a timezone‑aware datetime.
        max_retries: number of times to retry on transient errors.
        backoff_seconds: initial backoff delay for retries.

    Returns:
        A mapping from calendar ID to a list of (start, end) tuples in UTC.
    """
    service = get_calendar_service()
    body = {
        "timeMin": time_min.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timeMax": time_max.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "items": [{"id": cid} for cid in calendar_ids],
    }
    attempt = 0
    while True:
        try:
            response = service.freebusy().query(body=body).execute()
            break
        except HttpError as exc:
            attempt += 1
            # Retry on 5xx or rate‑limit errors.
            status = getattr(exc.resp, "status", None)
            if attempt <= max_retries and status in (429, 500, 502, 503, 504):
                delay = backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "FreeBusy query transient error (status=%s), retrying in %.1fs (attempt %s/%s)",
                    status,
                    delay,
                    attempt,
                    max_retries,
                )
                time.sleep(delay)
                continue
            logger.error("FreeBusy query failed after %s attempts: %s", attempt, exc)
            raise
    calendars: Dict[str, Any] = response.get("calendars", {})
    result: Dict[str, List[Tuple[datetime, datetime]]] = {}
    for cid, data in calendars.items():
        blocks: List[Tuple[datetime, datetime]] = []
        for block in data.get("busy", []):
            start = datetime.fromisoformat(block["start"].replace("Z", "+00:00")).astimezone(timezone.utc)
            end = datetime.fromisoformat(block["end"].replace("Z", "+00:00")).astimezone(timezone.utc)
            blocks.append((start, end))
        result[cid] = blocks
    return result