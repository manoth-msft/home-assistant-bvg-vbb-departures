"""BVG API client for fallback departures fetching.

Uses the unofficial BVG connection-search API endpoints:
- GET https://www.bvg.de/connection-search/v1/departureBoard
  ?lang=de&locationName=<stop-name>&maxJourneys=<count>
"""

import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

BVG_DEPARTURE_BOARD_URL = "https://www.bvg.de/connection-search/v1/departureBoard"
BVG_REFERER = "https://www.bvg.de/"


def _log_bvg_error(error_type: str, stop_name: str, error: Exception) -> None:
    """Log BVG API errors consistently."""
    if isinstance(error, aiohttp.ClientResponseError):
        _LOGGER.warning(
            "[BVG] HTTP error for stop '%s' (status=%s, message=%s)",
            stop_name,
            error.status,
            error.message,
        )
    elif isinstance(error, aiohttp.ClientConnectorError):
        _LOGGER.warning("[BVG] Connection error for stop '%s': %s", stop_name, error)
    elif isinstance(error, aiohttp.ServerDisconnectedError):
        _LOGGER.warning("[BVG] Server disconnected for stop '%s': %s", stop_name, error)
    elif isinstance(error, aiohttp.ClientError):
        _LOGGER.warning("[BVG] Client error for stop '%s': %s", stop_name, error)
    elif isinstance(error, TimeoutError):
        _LOGGER.warning("[BVG] Request timeout for stop '%s': %s", stop_name, error)
    else:
        _LOGGER.exception("[BVG] %s for stop '%s': %s", error_type, stop_name, error)


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
            "User-Agent": "Home Assistant BVG Integration",
        }
        params = {
            "lang": "de",
            "locationName": stop_name,
            "maxJourneys": max_journeys,
        }

        _LOGGER.debug(
            "[BVG] Querying departureBoard API for stop '%s' (maxJourneys=%s)",
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
                "[BVG] Received response from departureBoard API for stop '%s' (status=%s)",
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
