# mypy: disable-error-code="attr-defined,call-arg"
"""The Berlin (BVG) and Brandenburg (VBB) transport integration."""

from __future__ import annotations

import logging

from typing import Any
import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

from .const import (
    PRIM_API_ENDPOINT,
    SEC_API_ENDPOINT,
    API_MAX_RESULTS,
    PRIM_API_ENABLED,
    SEC_API_ENABLED,
    CONF_DEPARTURES_STOP_ID,
    CONF_DEPARTURES_NAME,
    CONF_SELECTED_STOP,
    CONF_DEPARTURES_DIRECTION,
    CONF_DEPARTURES_EXCLUDED_STOPS,
    CONF_DEPARTURES_WALKING_TIME,
    CONF_SHOW_API_LINE_COLORS,
    CONF_EXCLUDE_RINGBAHN_CLOCKWISE,
    CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE,
    CONF_REMOVE_BERLIN_SUFFIX,
    DOMAIN,
    DIRECTION_ID_MIGRATION_ENABLED,
    DIRECTION_MIGRATION_STATE,
    DIRECTION_DEBUG_KEEP_AS_TEXT,
    DIRECTION_DEBUG_MODE_ENABLED,
)

from .sensor import TRANSPORT_TYPES_SCHEMA

_LOGGER = logging.getLogger(__name__)

CONF_SEARCH = "search"
CONF_FOUND_STOPS = "found_stops"

DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEPARTURES_DIRECTION): cv.string,
        vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): cv.string,
        vol.Optional(CONF_DEPARTURES_WALKING_TIME, default=1): cv.positive_int,
        vol.Optional(CONF_SHOW_API_LINE_COLORS, default=False): cv.boolean,
        vol.Optional(CONF_EXCLUDE_RINGBAHN_CLOCKWISE, default=False): cv.boolean,
        vol.Optional(CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE, default=False): cv.boolean,
        vol.Optional(CONF_REMOVE_BERLIN_SUFFIX, default=False): cv.boolean,
        **TRANSPORT_TYPES_SCHEMA,
    }
)

NAME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SEARCH): cv.string,
    }
)


async def _try_fetch_stops_from_endpoint(  # pylint: disable=too-many-return-statements
    session: aiohttp.ClientSession, endpoint_url: str, endpoint_name: str, name: str
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Try to fetch stops from a specific endpoint.

    Attempts a single API endpoint and returns the results or None on failure.
    This allows the caller to fall back to the next endpoint.

    Args:
        session: aiohttp ClientSession for making HTTP requests
        endpoint_url: Base URL of the API endpoint
        endpoint_name: Name for logging ("primary" or "secondary")
        name: Stop name or partial name to search for

    Returns:
        Tuple of (stops, error_key) where:
        - stops: List of stops on success, None on failure
        - error_key: Error key if failed, None if successful
    """
    try:
        async with async_timeout.timeout(240):
            response = await session.get(
                url=f"{endpoint_url}/locations",
                params={
                    "query": name,
                    "results": API_MAX_RESULTS,
                },
            )
            response.raise_for_status()
            stops = await response.json()
    except aiohttp.ClientResponseError as ex:
        error_key = "api_rate_limited" if ex.status == 429 else "api_error"
        if error_key == "api_rate_limited":
            retry_after = ex.headers.get("Retry-After") if ex.headers else None
            _LOGGER.debug(
                "[config_flow] Stop search rate limited on %s (query=%s, retry_after=%s)",
                endpoint_name,
                name,
                retry_after,
            )
        else:
            _LOGGER.debug(
                "[config_flow] Stop search HTTP error on %s (query=%s, status=%s)",
                endpoint_name,
                name,
                ex.status,
            )
        return None, error_key
    except aiohttp.ClientConnectorError:
        _LOGGER.debug("[config_flow] %s unreachable (query=%s)", endpoint_name, name)
        return None, "api_unreachable"
    except aiohttp.ServerDisconnectedError:
        _LOGGER.debug("[config_flow] %s disconnected (query=%s)", endpoint_name, name)
        return None, "api_disconnected"
    except aiohttp.ClientError:
        _LOGGER.debug("[config_flow] %s client error (query=%s)", endpoint_name, name)
        return None, "api_error"
    except TimeoutError:
        _LOGGER.debug("[config_flow] %s timeout (query=%s)", endpoint_name, name)
        return None, "api_timeout"
    except Exception as ex:  # pylint: disable=broad-exception-caught
        _LOGGER.debug(
            "[config_flow] Unexpected error on %s (query=%s): %s",
            endpoint_name,
            name,
            ex,
        )
        return None, "api_unexpected_error"

    if not isinstance(stops, list):
        _LOGGER.debug(
            "[config_flow] %s returned unexpected payload type for query '%s'",
            endpoint_name,
            name,
        )
        return None, None

    # Convert API data into our format
    result = [
        {CONF_DEPARTURES_NAME: stop["name"], CONF_DEPARTURES_STOP_ID: stop["id"]}
        for stop in stops
        if stop["type"] == "stop"
    ]

    _LOGGER.debug(
        "[config_flow] Found %s stops on %s for query '%s'",
        len(result),
        endpoint_name,
        name,
    )
    return result, None


async def get_stop_id(
    session: aiohttp.ClientSession, name: str
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Search for VBB stops by name with dual-API failover.

    Attempts to fetch stops from primary endpoint first, then secondary
    endpoint if primary fails. Returns immediately on success from either.

    Args:
        session: aiohttp ClientSession for making HTTP requests
        name: Stop name or partial name to search for

    Returns:
        Tuple of (success, stops, error_key) where:
        - success: True if API call succeeded (even if no results found)
        - stops: List of matching stops with 'name' and 'id' fields
        - error_key: String key for error message (e.g. "api_rate_limited") or None if successful
    """
    error_key: str | None = None
    primary_or_secondary_error: str | None = "api_error"

    # Try primary endpoint first (if enabled)
    if PRIM_API_ENABLED:
        stops, error_key = await _try_fetch_stops_from_endpoint(
            session, PRIM_API_ENDPOINT, "primary", name
        )
        if error_key is None:
            # Primary succeeded (with or without results)
            return True, stops or [], None

    # Primary failed or disabled, try secondary endpoint (if enabled)
    if SEC_API_ENABLED:
        stops, secondary_error = await _try_fetch_stops_from_endpoint(
            session, SEC_API_ENDPOINT, "secondary", name
        )
        if secondary_error is None:
            # Secondary succeeded (with or without results)
            return True, stops or [], None
        # Secondary failed, use its error for reporting
        primary_or_secondary_error = secondary_error
    else:
        # Secondary disabled, use primary error if we have it
        primary_or_secondary_error = error_key or "api_error"

    # Both endpoints failed or disabled, return the appropriate error
    _LOGGER.warning(
        "[config_flow] Stop search failed on both endpoints "
        "(query=%s, primary_enabled=%s, secondary_enabled=%s)",
        name,
        PRIM_API_ENABLED,
        SEC_API_ENABLED,
    )
    return False, [], primary_or_secondary_error


def list_stops(stops: list[dict[str, Any]]) -> vol.Schema:
    """Create a dropdown schema for selecting from a list of stops.

    Args:
        stops: List of stop dictionaries containing CONF_DEPARTURES_NAME and
               CONF_DEPARTURES_STOP_ID keys

    Returns:
        Voluptuous schema with a required dropdown selector containing stop options.
    """
    schema = vol.Schema(
        {
            vol.Required(CONF_SELECTED_STOP): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        f"{stop[CONF_DEPARTURES_NAME]} [{stop[CONF_DEPARTURES_STOP_ID]}]"
                        for stop in stops
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )

    return schema


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
            error_key = "api_rate_limited" if ex.status == 429 else "api_error"
            _LOGGER.debug(
                "[config_flow] Direction stop search failed on primary (query=%s, status=%s)",
                name,
                ex.status,
            )
        except (aiohttp.ClientError, TimeoutError) as ex:
            error_key = "api_error"
            _LOGGER.debug(
                "[config_flow] Direction stop search error on primary (query=%s): %s",
                name,
                ex,
            )
        except Exception as ex:  # pylint: disable=broad-exception-caught
            error_key = "api_error"
            _LOGGER.debug(
                "[config_flow] Unexpected error in direction search on primary: %s", ex
            )
        else:
            # Primary succeeded
            if isinstance(stops, list):
                result = [
                    {"name": stop["name"], "id": stop["id"]}
                    for stop in stops
                    if stop["type"] == "stop"
                ]
                _LOGGER.debug(
                    "[config_flow] Found %s direction stops on primary for query '%s'",
                    len(result),
                    name,
                )
                return True, result, None
            else:
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
                "[config_flow] Direction stop search failed on secondary (query=%s): %s",
                name,
                ex,
            )
            primary_or_secondary_error = error_key or "api_error"
        else:
            # Secondary succeeded
            if isinstance(stops, list):
                result = [
                    {"name": stop["name"], "id": stop["id"]}
                    for stop in stops
                    if stop["type"] == "stop"
                ]
                _LOGGER.debug(
                    "[config_flow] Found %s direction stops on secondary for query '%s'",
                    len(result),
                    name,
                )
                return True, result, None
            else:
                primary_or_secondary_error = "api_error"

    _LOGGER.warning(
        "[config_flow] Direction stop search failed on both endpoints (query=%s)",
        name,
    )
    return False, [], primary_or_secondary_error


class TransportConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Init the ConfigFlow."""
        self.data: dict[str, Any] = {}
        self._direction_stop: dict[str, Any] | None = None  # For direction steps

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=NAME_SCHEMA,
                errors={},
            )

        session = async_get_clientsession(self.hass)
        success, stops, error_key = await get_stop_id(
            session, user_input[CONF_SEARCH]
        )

        # If API call failed, show error message and ask to retry
        if not success:
            _LOGGER.warning(
                "[config_flow] Stop search failed for query '%s': %s",
                user_input[CONF_SEARCH],
                error_key,
            )
            return self.async_show_form(
                step_id="user",
                data_schema=NAME_SCHEMA,
                errors={"base": error_key},
            )

        # If no stops found (but API succeeded)
        if not stops:
            _LOGGER.debug(
                "[config_flow] No stops found for query '%s'",
                user_input[CONF_SEARCH],
            )
            return self.async_show_form(
                step_id="user",
                data_schema=NAME_SCHEMA,
                errors={"base": "no_stops_found"},
                description_placeholders={
                    "search_query": user_input[CONF_SEARCH],
                },
            )

        # Stops found, proceed to selection
        self.data[CONF_FOUND_STOPS] = stops
        _LOGGER.debug(
            "[config_flow] Found stops for query '%s': %s stops",
            user_input[CONF_SEARCH],
            len(stops),
        )

        return await self.async_step_stop()

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle stop selection from search results."""
        if user_input is None:
            # Safety check: should never happen because we validate in async_step_user
            if not self.data.get(CONF_FOUND_STOPS):
                return self.async_show_form(
                    step_id="user",
                    data_schema=NAME_SCHEMA,
                    errors={},
                )

            return self.async_show_form(
                step_id="stop",
                data_schema=list_stops(self.data[CONF_FOUND_STOPS]),
                errors={},
            )

        selected_stop = next(
            (
                (stop[CONF_DEPARTURES_NAME], stop[CONF_DEPARTURES_STOP_ID])
                for stop in self.data[CONF_FOUND_STOPS]
                if user_input[CONF_SELECTED_STOP]
                == f"{stop[CONF_DEPARTURES_NAME]} [{stop[CONF_DEPARTURES_STOP_ID]}]"
            ),
            None,
        )
        if selected_stop is None:
            return self.async_show_form(
                step_id="stop",
                data_schema=list_stops(self.data[CONF_FOUND_STOPS]),
                errors={},
            )
        (
            self.data[CONF_DEPARTURES_NAME],
            self.data[CONF_DEPARTURES_STOP_ID],
        ) = selected_stop
        _LOGGER.debug("[config_flow] Selected stop '%s' [%s]", selected_stop[0], selected_stop[1])

        return await self.async_step_direction_input()

    async def async_step_direction_input(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle optional direction filter input."""
        if user_input is None:
            return self.async_show_form(
                step_id="direction_input",
                data_schema=vol.Schema({
                    vol.Optional("direction_name"): cv.string,
                }),
                description_placeholders={
                    "main_stop": self.data.get(CONF_DEPARTURES_NAME, "Unknown"),
                },
            )

        direction_name = user_input.get("direction_name", "").strip()

        # User didn't enter anything → skip direction and go to details
        if not direction_name:
            return await self.async_step_details()

        # Search for direction stops
        session = async_get_clientsession(self.hass)
        success, stops, error_key = await get_direction_stops(
            session, direction_name, results=5
        )

        # API call failed
        if not success:
            _LOGGER.warning(
                "[config_flow] Direction search failed (query=%s): %s",
                direction_name,
                error_key,
            )
            return self.async_show_form(
                step_id="direction_input",
                data_schema=vol.Schema({
                    vol.Optional("direction_name"): cv.string,
                }),
                errors={"base": error_key},
            )

        # No stops found
        if not stops:
            _LOGGER.debug(
                "[config_flow] No direction stops found for query '%s'",
                direction_name,
            )
            return self.async_show_form(
                step_id="direction_input",
                data_schema=vol.Schema({
                    vol.Optional("direction_name"): cv.string,
                }),
                errors={"base": "stop_not_found"},
                description_placeholders={"search_query": direction_name},
            )

        # Store candidates for later steps
        self.data["direction_candidates"] = stops
        self.data["direction_name"] = direction_name

        # Single match → go directly to validation
        if len(stops) == 1:
            self._direction_stop = stops[0]
            return await self.async_step_direction_validate()

        # Multiple matches → ask user to select
        return await self.async_step_direction_select()

    async def async_step_direction_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle direction stop selection when multiple matches found."""
        if user_input is None:
            options = [
                f"{s['name']} [{s['id']}]" for s in self.data["direction_candidates"]
            ]
            return self.async_show_form(
                step_id="direction_select",
                data_schema=vol.Schema({
                    vol.Required("selected_stop"): vol.In(options),
                }),
            )

        selected_text = user_input["selected_stop"]
        # Parse "Station Name [900083101]" → extract ID
        stop_id = selected_text.split("[")[-1].rstrip("]")

        self._direction_stop = {
            "id": stop_id,
            "name": selected_text.split(" [")[0],
        }

        return await self.async_step_direction_validate()

    async def async_step_direction_validate(self) -> FlowResult:
        """Validate that direction stop exists on the main stop's route."""
        if self._direction_stop is None:
            _LOGGER.error("[config_flow] direction_validate called but _direction_stop is None")
            return await self.async_step_details()

        main_stop_id = self.data.get(CONF_DEPARTURES_STOP_ID)
        direction_id = self._direction_stop["id"]
        direction_name = self._direction_stop["name"]

        # DEBUG-MODE: Keep certain stops as text for testing
        if DIRECTION_DEBUG_MODE_ENABLED and direction_name in DIRECTION_DEBUG_KEEP_AS_TEXT:
            _LOGGER.warning(
                "[config_flow] DEBUG-MODE: Direction '%s' will be saved as TEXT, not Stop-ID!",
                direction_name,
            )
            self.data[CONF_DEPARTURES_DIRECTION] = direction_name  # Save as text
            return await self.async_step_details()

        try:
            session = async_get_clientsession(self.hass)

            # Query trips to validate direction stop is on route
            trips_url = f"{PRIM_API_ENDPOINT}/trips"
            params = {
                "currentlyStoppingAt": main_stop_id,
                "fromWhen": "today",
                "untilWhen": "next week",
                "stopovers": "true",
            }

            async with async_timeout.timeout(30):
                response = await session.get(trips_url, params=params)
                response.raise_for_status()
                trips = await response.json()

            # Check if direction_id appears in any trip's stopovers
            found = False
            if isinstance(trips, list):
                for trip in trips:
                    stopovers = trip.get("stopovers", [])
                    if any(
                        stop.get("stop", {}).get("id") == direction_id
                        for stop in stopovers
                    ):
                        found = True
                        break

            if not found:
                _LOGGER.warning(
                    "[config_flow] Direction stop '%s' [%s] not found on trips from '%s'",
                    direction_name,
                    direction_id,
                    self.data.get(CONF_DEPARTURES_NAME),
                )
                # Still save it, but log warning

            # Save the direction Stop-ID
            self.data[CONF_DEPARTURES_DIRECTION] = direction_id
            return await self.async_step_details()

        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOGGER.error(
                "[config_flow] Direction validation failed (direction=%s): %s",
                direction_name,
                ex,
            )
            # On error, still save the Stop-ID (don't block)
            self.data[CONF_DEPARTURES_DIRECTION] = direction_id
            return await self.async_step_details()

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the details."""
        if user_input is None:
            return self.async_show_form(
                step_id="details",
                data_schema=DATA_SCHEMA,
                errors={},
            )

        data = user_input
        data[CONF_DEPARTURES_STOP_ID] = self.data[CONF_DEPARTURES_STOP_ID]
        data[CONF_DEPARTURES_NAME] = self.data[CONF_DEPARTURES_NAME]

        # Preserve direction from direction-steps if it was set
        if CONF_DEPARTURES_DIRECTION in self.data and self.data[CONF_DEPARTURES_DIRECTION]:
            data[CONF_DEPARTURES_DIRECTION] = self.data[CONF_DEPARTURES_DIRECTION]

        return self.async_create_entry(
            title=f"{data[CONF_DEPARTURES_NAME]} [{data[CONF_DEPARTURES_STOP_ID]}]",
            data=data,
        )
