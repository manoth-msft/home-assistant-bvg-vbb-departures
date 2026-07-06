"""BVG API response parser for departures.

Converts BVG departureBoard API responses to Departure objects.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any

from .departure import Departure
from .const import TRANSPORT_TYPE_VISUALS, DEFAULT_ICON

_LOGGER = logging.getLogger(__name__)


def _parse_iso_duration(duration_str: str) -> int:
    """Parse ISO-8601 duration string to seconds.

    Examples:
        PT1M -> 60
        PT5M -> 300
        PT-1M -> -60
        PT0S -> 0

    Args:
        duration_str: ISO-8601 duration string

    Returns:
        Total seconds (int). Returns 0 if parsing fails.
    """
    if not duration_str:
        return 0

    # Pattern: PT[+/-]?(\d+H)?(\d+M)?(\d+S)?
    match = re.match(r"^PT(-?)(\d+H)?(\d+M)?(\d+S)?$", duration_str)
    if not match:
        _LOGGER.debug("Failed to parse ISO duration: %s", duration_str)
        return 0

    is_negative = match.group(1) == "-"
    hours = int(match.group(2)[:-1]) if match.group(2) else 0
    minutes = int(match.group(3)[:-1]) if match.group(3) else 0
    seconds = int(match.group(4)[:-1]) if match.group(4) else 0

    total_seconds = (hours * 3600) + (minutes * 60) + seconds
    return -total_seconds if is_negative else total_seconds


def parse_bvg_departures(
    response: dict[str, Any] | list[Any],
    stop_name: str,
) -> list[Departure]:
    """Parse BVG departureBoard API response into Departure objects.

    Args:
        response: JSON response from BVG API
        stop_name: Stop name (for filtering/logging)

    Returns:
        List of Departure objects.
    """
    departures: list[Departure] = []

    # BVG response can be a dict with "date" key or a list
    if isinstance(response, dict):
        elements = response.get("elements", [])
    elif isinstance(response, list):
        # If response is a list of dicts with "elements"
        elements = []
        for item in response:
            if isinstance(item, dict) and "elements" in item:
                elements.extend(item["elements"])
    else:
        _LOGGER.warning("BVG response has unexpected type: %s", type(response))
        return departures

    for element in elements:
        try:
            departure = _parse_bvg_element(element, stop_name)
            if departure:
                departures.append(departure)
        except (KeyError, TypeError, ValueError) as ex:
            _LOGGER.debug("Skipping malformed BVG element: %s", ex)

    return departures


def _parse_bvg_element(element: dict[str, Any], stop_name: str) -> Departure | None:
    """Parse single BVG element to Departure object.

    Args:
        element: Single element from BVG response
        stop_name: Stop name for filtering

    Returns:
        Departure object or None if parsing fails.
    """
    service = element.get("service", {})
    departure_info = element.get("departure", {})

    if not service or not departure_info:
        return None

    # Extract basic fields
    line_name = service.get("name")
    line_type_name = service.get("lineTypeName")
    direction = service.get("direction")

    if not line_name or not line_type_name:
        return None

    # Map BVG line type to our line type
    line_type = _map_bvg_line_type(line_type_name)

    # Compose timestamp from date + time
    date_str = departure_info.get("date")
    time_str = departure_info.get("time")

    if not date_str or not time_str:
        _LOGGER.debug("Missing date or time in BVG element")
        return None

    try:
        # Format: 2026-07-04 and 00:42:00
        timestamp_str = f"{date_str}T{time_str}"
        # BVG uses Europe/Berlin timezone (UTC+2 in summer, UTC+1 in winter)
        # Parse as naive datetime, then assume Europe/Berlin
        timestamp = datetime.fromisoformat(timestamp_str).replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError) as ex:
        _LOGGER.debug("Failed to parse BVG timestamp (%s %s): %s", date_str, time_str, ex)
        return None

    # Parse delay from ISO-8601 duration
    delay_str = departure_info.get("delay", "PT0S")
    delay_seconds = _parse_iso_duration(delay_str)

    # Get visual properties
    line_visuals = TRANSPORT_TYPE_VISUALS.get(line_type) or {}

    # Generate trip ID (BVG doesn't provide it, so use hash of departure info)
    trip_id = f"bvg_{line_name}_{timestamp.isoformat()}_{direction}"

    return Departure(
        trip_id=trip_id,
        line_name=line_name,
        line_type=line_type,
        timestamp=timestamp,
        time=timestamp.strftime("%H:%M"),
        direction=direction,
        icon=line_visuals.get("icon") or DEFAULT_ICON,
        bg_color=None,  # BVG API doesn't provide colors
        fallback_color=line_visuals.get("color"),
        location=None,  # BVG API doesn't provide location
        cancelled=False,  # BVG API doesn't provide cancellation info
        delay=delay_seconds if delay_seconds else None,
        warnings=None,  # BVG API doesn't provide warnings
    )


def _map_bvg_line_type(bvg_line_type: str) -> str:
    """Map BVG line type name to standard line type.

    BVG uses: bus, tram, subway, suburban, regional, regionalExp, 
              longDistance, express

    Our types: bus, tram, subway, suburban, regional, express, ice

    Args:
        bvg_line_type: BVG line type name

    Returns:
        Standard line type string.
    """
    mapping = {
        "bus": "bus",
        "tram": "tram",
        "subway": "subway",
        "suburban": "suburban",
        "regional": "regional",
        "regionalExp": "regional",
        "express": "express",
        "longDistance": "ice",
    }
    return mapping.get(bvg_line_type, "bus")
