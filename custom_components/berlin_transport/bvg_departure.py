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
    direction_filter: str | None = None,
    transport_type_filters: dict[str, bool] | None = None,
) -> list[Departure]:
    """Parse BVG departureBoard API response into Departure objects.
    
    Optionally filters departures by direction and transport type to match
    the behavior of the transport.rest API.

    Args:
        response: JSON response from BVG API
        direction_filter: Optional direction string (e.g., "Hauptbahnhof").
                         If provided, only departures matching this direction are returned.
                         None means no direction filtering (return all).
        transport_type_filters: Optional dict mapping line_type to bool.
                               Keys: 'suburban', 'subway', 'tram', 'bus', 'ferry', 'express', 'regional'
                               If provided, only departures with enabled types are returned.
                               None means no transport type filtering (return all).

    Returns:
        List of Departure objects, optionally filtered by direction and transport type.
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
            departure = _parse_bvg_element(element)
            if departure:
                departures.append(departure)
        except (KeyError, TypeError, ValueError) as ex:
            _LOGGER.debug("Skipping malformed BVG element: %s", ex)

    # Apply optional direction and transport type filters
    if direction_filter or transport_type_filters:
        departures = _filter_departures_by_type_and_direction(
            departures,
            direction_filter=direction_filter,
            transport_type_filters=transport_type_filters,
        )

    return departures


def _parse_bvg_element(element: dict[str, Any]) -> Departure | None:
    """Parse single BVG element to Departure object.

    Args:
        element: Single element from BVG response

    Returns:
        Departure object or None if parsing fails.
    """
    service = element.get("service", {})
    departure_info = element.get("departure", {})

    if not service or not departure_info:
        return None

    # Extract and validate basic fields
    line_name = service.get("name")
    line_type_name = service.get("lineTypeName")
    direction = service.get("direction")

    if not line_name or not line_type_name:
        return None

    # Validate and compose timestamp
    date_str = departure_info.get("date")
    time_str = departure_info.get("time")

    if not date_str or not time_str:
        _LOGGER.debug("Missing date or time in BVG element")
        return None

    try:
        timestamp_str = f"{date_str}T{time_str}"
        timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as ex:
        _LOGGER.debug(
            "Failed to parse BVG timestamp (%s %s): %s", date_str, time_str, ex
        )
        return None

    # Map line type and get visuals
    line_type = _map_bvg_line_type(line_type_name)
    line_visuals = TRANSPORT_TYPE_VISUALS.get(line_type) or {}

    # Generate trip ID and parse delay
    trip_id = f"bvg_{line_name}_{timestamp.isoformat()}_{direction}"
    delay_seconds = _parse_iso_duration(departure_info.get("delay", "PT0S"))

    return Departure(
        trip_id=trip_id,
        line_name=line_name,
        line_type=line_type,
        timestamp=timestamp,
        time=timestamp.strftime("%H:%M"),
        direction=direction,
        icon=line_visuals.get("icon") or DEFAULT_ICON,
        bg_color=None,
        fallback_color=line_visuals.get("color"),
        location=None,
        cancelled=False,
        delay=delay_seconds if delay_seconds else None,
        warnings=None,
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


def _filter_departures_by_type_and_direction(
    departures: list[Departure],
    direction_filter: str | None = None,
    transport_type_filters: dict[str, bool] | None = None,
) -> list[Departure]:
    """Filter departures by direction and transport type (CLIENT-SIDE).
    
    This function implements the filtering that the transport.rest API does
    server-side, but must be done client-side for the BVG API which doesn't
    support filtering parameters.
    
    Args:
        departures: List of parsed Departure objects
        direction_filter: Direction string to match (e.g., "Hauptbahnhof").
                         If provided, only departures matching this direction are kept.
        transport_type_filters: Dict mapping line_type to bool.
                               If provided, only departures with enabled types are kept.
    
    Returns:
        Filtered list of Departure objects.
    """
    filtered = departures
    
    # Apply direction filter (if configured)
    if direction_filter:
        filtered = [
            d for d in filtered
            if d.direction and direction_filter.lower() in d.direction.lower()
        ]
    
    # Apply transport type filter (if configured)
    if transport_type_filters:
        filtered = [
            d for d in filtered
            if transport_type_filters.get(d.line_type, False)
        ]
    
    return filtered
