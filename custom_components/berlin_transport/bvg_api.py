"""BVG API client for fallback departures fetching.

Uses the unofficial BVG connection-search API endpoints:
- GET https://www.bvg.de/connection-search/v1/departureBoard
  ?lang=de&locationName=<stop-name>&maxJourneys=<count>
"""

import logging
from typing import Any

import aiohttp
import async_timeout

from .bvg_departure import parse_bvg_departures
from .const import API_USER_AGENT, BVG_API_ENDPOINT, BVG_API_REFERER
from .departure import Departure

_LOGGER = logging.getLogger(__name__)


def _log_bvg_error(error_type: str, stop_name: str, error: Exception) -> None:
    """Log BVG API errors consistently."""
    if isinstance(error, aiohttp.ClientResponseError):
        _LOGGER.warning(
            "[bvg_api] HTTP error for stop '%s' (status=%s)",
            stop_name,
            error.status,
        )
    elif isinstance(error, aiohttp.ClientConnectorError):
        _LOGGER.warning("[bvg_api] Connection error for stop '%s': %s", stop_name, error)
    elif isinstance(error, aiohttp.ServerDisconnectedError):
        _LOGGER.warning("[bvg_api] Server disconnected for stop '%s': %s", stop_name, error)
    elif isinstance(error, aiohttp.ClientError):
        _LOGGER.warning("[bvg_api] Client error for stop '%s': %s", stop_name, error)
    elif isinstance(error, TimeoutError):
        _LOGGER.warning("[bvg_api] Request timeout for stop '%s': %s", stop_name, error)
    else:
        _LOGGER.exception("[bvg_api] %s for stop '%s': %s", error_type, stop_name, error)


async def fetch_bvg_departures(
    session: aiohttp.ClientSession,
    stop_name: str,
    max_journeys: int = 30,
    timeout_seconds: int = 240,
) -> dict[str, Any] | None:
    """Fetch departures from BVG departureBoard API.

    Args:
        session: aiohttp ClientSession
        stop_name: Stop name (not ID)
        max_journeys: Maximum number of journeys to return
        timeout_seconds: Request timeout in seconds

    Returns:
        JSON response dict or None on error.
    """
    try:
        headers = {
            "Referer": BVG_API_REFERER,
            "User-Agent": API_USER_AGENT,
        }
        params = {
            "lang": "de",
            "locationName": stop_name,
            "maxJourneys": max_journeys,
        }

        _LOGGER.debug(
            "[bvg_api] Querying departureBoard API for stop '%s' (maxJourneys=%s)",
            stop_name,
            max_journeys,
        )

        async with async_timeout.timeout(timeout_seconds):
            response = await session.get(
                url=BVG_API_ENDPOINT,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            result = await response.json()
            _LOGGER.debug(
                "[bvg_api] Received response from departureBoard API for stop '%s' (status=%s)",
                stop_name,
                response.status,
            )
            return result

    except (
        aiohttp.ClientResponseError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerDisconnectedError,
        aiohttp.ClientError,
        TimeoutError,
    ) as ex:
        _log_bvg_error("BVG API error", stop_name, ex)
        return None


async def fetch_and_parse_bvg_departures(
    session: aiohttp.ClientSession,
    stop_name: str,
    max_journeys: int = 30,
    timeout_seconds: int = 240,
    transport_type_filters: dict[str, bool] | None = None,
) -> list[Departure] | None:
    """Fetch and parse BVG departures with optional transport type filtering.
    
    Combines fetch_bvg_departures() and parse_bvg_departures() into a
    single call, applying only transport type filters (no direction filtering,
    as BVG API filters by final destination, not intermediate stops).

    Args:
        session: aiohttp ClientSession
        stop_name: Stop name (not ID)
        max_journeys: Maximum number of journeys to return
        timeout_seconds: Request timeout in seconds
        transport_type_filters: Optional dict mapping line_type to bool.
                               Keys: 'suburban', 'subway', 'tram', 'bus',
                               'ferry', 'express', 'regional'. If provided,
                               only departures with enabled types returned.
                               None = no transport type filtering (all types).
    
    Returns:
        Filtered list of Departure objects, or None if API request fails.
    """
    response = await fetch_bvg_departures(
        session=session,
        stop_name=stop_name,
        max_journeys=max_journeys,
        timeout_seconds=timeout_seconds,
    )
    
    if response is None:
        return None
    
    # Parse with transport type filtering only
    filtered_departures = parse_bvg_departures(
        response=response,
        transport_type_filters=transport_type_filters,
    )
    
    # Also parse without filtering to show pre-filter count for logging
    if transport_type_filters:
        unfiltered_departures = parse_bvg_departures(
            response=response,
            transport_type_filters=None,
        )
        
        if unfiltered_departures:
            # Build summary by line_type
            enabled_types = [k for k, v in transport_type_filters.items() if v]
            type_counts: dict[str, int] = {}
            for d in unfiltered_departures:
                type_counts[d.line_type] = type_counts.get(d.line_type, 0) + 1
            
            if len(unfiltered_departures) != len(filtered_departures):
                _LOGGER.debug(
                    "[bvg_api] Filtering for stop '%s': %d raw departures → %d after filtering "
                    "(enabled_types=%s, breakdown_raw=%s)",
                    stop_name,
                    len(unfiltered_departures),
                    len(filtered_departures),
                    enabled_types,
                    type_counts,
                )
    
    return filtered_departures
