"""Shared utilities for berlin_transport integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .const import (
    PRIM_API_ENDPOINT,
    SEC_API_ENDPOINT,
    API_REQUEST_TIMEOUT,
    PRIM_API_ENABLED,
    SEC_API_ENABLED,
    CONF_TYPE_SUBURBAN,
    CONF_TYPE_SUBWAY,
    CONF_TYPE_TRAM,
    CONF_TYPE_BUS,
    CONF_TYPE_FERRY,
    CONF_TYPE_EXPRESS,
    CONF_TYPE_REGIONAL,
)

_LOGGER = logging.getLogger(__name__)

# Configuration validation constants
MAX_EXCLUDED_STOPS_LENGTH = 255  # Entity ID safe length
MAX_WALKING_TIME = 60  # minutes


def validate_excluded_stops(value: str) -> str:
    """Validate excluded_stops configuration value.

    Ensures the comma-separated Stop-IDs list doesn't overflow entity ID
    and contains only valid characters. Home Assistant entity IDs have a max
    length of 255 characters, and excluded_stops is part of the entity ID
    calculation.

    Args:
        value: Comma-separated Stop-IDs string (e.g. "900078201,900190001")

    Returns:
        Validated string (unchanged if valid)

    Raises:
        vol.Invalid: If validation fails (length exceeded, invalid format, etc.)
    """
    if not value or not value.strip():
        # Empty is OK (no exclusions)
        return ""

    # Check length limit
    if len(value) > MAX_EXCLUDED_STOPS_LENGTH:
        raise vol.Invalid(
            f"excluded_stops too long ({len(value)}/{MAX_EXCLUDED_STOPS_LENGTH} chars). "
            "Please use fewer Stop-IDs (max ~20 stops)."
        )

    # Validate format: comma-separated numbers with optional whitespace
    stops = [s.strip() for s in value.split(",")]
    for stop in stops:
        if not stop:
            raise vol.Invalid(
                "excluded_stops: Empty stop ID found. "
                "Use format: '900078201,900190001' (no spaces inside IDs)"
            )
        if not stop.isdigit():
            raise vol.Invalid(
                f"excluded_stops: Invalid Stop-ID '{stop}'. "
                "Must be numeric (e.g. '900078201')"
            )
        if len(stop) > 20:
            raise vol.Invalid(
                f"excluded_stops: Stop-ID '{stop}' too long (max 20 digits)"
            )

    return value


def validate_walking_time(value: int) -> int:
    """Validate walking_time configuration value.

    Ensures walking time is within reasonable bounds (0-60 minutes).

    Args:
        value: Walking time in minutes

    Returns:
        Validated integer

    Raises:
        vol.Invalid: If out of bounds
    """
    if not isinstance(value, int):
        raise vol.Invalid("walking_time must be a number")

    if value < 0:
        raise vol.Invalid("walking_time cannot be negative")

    if value > MAX_WALKING_TIME:
        raise vol.Invalid(
            f"walking_time too high ({value}/{MAX_WALKING_TIME} min). "
            "Using max 60 minutes."
        )

    return value


TRANSPORT_TYPES_SCHEMA = {
    vol.Optional(CONF_TYPE_SUBURBAN, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_SUBWAY, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_TRAM, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_BUS, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_FERRY, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_EXPRESS, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_REGIONAL, default=True): cv.boolean,
}


async def get_direction_stops(
    session: aiohttp.ClientSession, name: str, results: int = 5
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Search for direction stops with customizable result limit.

    Like get_stop_id but with adjustable results parameter for direction filtering.
    Returns stops with full product information for later filtering.

    Args:
        session: aiohttp ClientSession
        name: Stop name to search for
        results: Number of results to return (default 5)

    Returns:
        Tuple of (success, stops, error_key)
    """
    error_key: str | None = None
    primary_or_secondary_error: str | None = "api_error"

    # Try primary endpoint first
    if PRIM_API_ENABLED:
        try:
            async with async_timeout.timeout(API_REQUEST_TIMEOUT):
                response = await session.get(
                    url=f"{PRIM_API_ENDPOINT}/locations",
                    params={
                        "query": name,
                        "results": results,
                    },
                )
                response.raise_for_status()
                stops = await response.json()
        except aiohttp.ClientResponseError as ex:
            error_key = (
                "api_rate_limited" if ex.status == 429 else "api_error"
            )
            _LOGGER.debug(
                (
                    "[direction] Stop search failed on primary "
                    "(query=%s, status=%s)"
                ),
                name,
                ex.status,
            )
        except (aiohttp.ClientError, TimeoutError) as ex:
            error_key = "api_error"
            _LOGGER.debug(
                "[direction] Stop search error on primary (query=%s): %s",
                name,
                ex,
            )
        except Exception as ex:  # pylint: disable=broad-exception-caught
            error_key = "api_error"
            _LOGGER.debug(
                "[direction] Unexpected error in stop search on primary: %s",
                ex,
            )
        if error_key is None:
            # Primary succeeded
            if isinstance(stops, list):
                result = [
                    {"name": stop["name"], "id": stop["id"]}
                    for stop in stops
                    if stop["type"] == "stop"
                ]
                _LOGGER.debug(
                    (
                        "[direction] Found %s direction stops on primary "
                        "for query '%s'"
                    ),
                    len(result),
                    name,
                )
                return True, result, None
            error_key = "api_error"

    # Primary failed/disabled, try secondary
    if SEC_API_ENABLED:
        try:
            async with async_timeout.timeout(API_REQUEST_TIMEOUT):
                response = await session.get(
                    url=f"{SEC_API_ENDPOINT}/locations",
                    params={
                        "query": name,
                        "results": results,
                    },
                )
                response.raise_for_status()
                stops = await response.json()
        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOGGER.debug(
                (
                    "[direction] Stop search failed on secondary "
                    "(query=%s): %s"
                ),
                name,
                ex,
            )
            primary_or_secondary_error = error_key or "api_error"
        if error_key is None:
            # Secondary succeeded
            if isinstance(stops, list):
                result = [
                    {"name": stop["name"], "id": stop["id"]}
                    for stop in stops
                    if stop["type"] == "stop"
                ]
                _LOGGER.debug(
                    (
                        "[direction] Found %s direction stops on secondary "
                        "for query '%s'"
                    ),
                    len(result),
                    name,
                )
                return True, result, None
            primary_or_secondary_error = "api_error"

    _LOGGER.warning(
        "[direction] Stop search failed on both endpoints (query=%s)",
        name,
    )
    return False, [], primary_or_secondary_error
