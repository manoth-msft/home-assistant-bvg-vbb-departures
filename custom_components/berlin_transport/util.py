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

# Shared schema for transport type configuration
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
            async with async_timeout.timeout(240):
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
            async with async_timeout.timeout(240):
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
