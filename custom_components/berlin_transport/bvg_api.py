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
from .const import API_USER_AGENT
from .departure import Departure

_LOGGER = logging.getLogger(__name__)

BVG_DEPARTURE_BOARD_URL = "https://www.bvg.de/connection-search/v1/departureBoard"
BVG_REFERER = "https://www.bvg.de/"


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
            "Referer": BVG_REFERER,
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
                url=BVG_DEPARTURE_BOARD_URL,
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


async def fetch_and_parse_bvg_departures(  # pylint: disable=too-many-positional-arguments
    session: aiohttp.ClientSession,
    stop_name: str,
    max_journeys: int = 30,
    timeout_seconds: int = 240,
    direction_filter: str | None = None,
    transport_type_filters: dict[str, bool] | None = None,
) -> list[Departure] | None:
    """Fetch and parse BVG departures with optional filtering.
    
    Combines fetch_bvg_departures() and parse_bvg_departures() into a
    single call, applying direction and transport type filters to match
    transport.rest API filtering behavior.
    
    Args:
        session: aiohttp ClientSession
        stop_name: Stop name (not ID)
        max_journeys: Maximum number of journeys to return
        timeout_seconds: Request timeout in seconds
        direction_filter: Optional direction string (e.g., "Hauptbahnhof").
                         Only departures matching this direction.
                         None = no direction filtering.
        transport_type_filters: Optional dict mapping line_type to bool.
                               Keys: 'suburban', 'subway', 'tram', 'bus',
                               'ferry', 'express', 'regional'. If provided,
                               only departures with enabled types returned.
                               None = no transport type filtering.
    
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
    
    return parse_bvg_departures(
        response=response,
        direction_filter=direction_filter,
        transport_type_filters=transport_type_filters,
    )
