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
    API_ENDPOINT,
    API_MAX_RESULTS,
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
    DOMAIN,  # noqa
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


async def get_stop_id(
    session: aiohttp.ClientSession, name: str
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Search for VBB stops by name using the transport.rest API.
    
    Args:
        session: aiohttp ClientSession for making HTTP requests
        name: Stop name or partial name to search for
        
    Returns:
        Tuple of (success, stops, error_key) where:
        - success: True if API call succeeded (even if no results found)
        - stops: List of matching stops with 'name' and 'id' fields
        - error_key: String key for error message (e.g. "api_rate_limited") or None if successful
    """
    stops: Any = []
    error_key = None
    
    try:
        async with async_timeout.timeout(240):
            response = await session.get(
                url=f"{API_ENDPOINT}/locations",
                params={
                    "query": name,
                    "results": API_MAX_RESULTS,
                },
            )
            response.raise_for_status()
            stops = await response.json()
    except aiohttp.ClientResponseError as ex:
        if ex.status == 429:
            error_key = "api_rate_limited"
            retry_after = ex.headers.get("Retry-After") if ex.headers else None
            _LOGGER.warning(
                "[config_flow] Stop search rate limited (query=%s, status=%s, retry_after=%s)",
                name,
                ex.status,
                retry_after,
            )
        else:
            error_key = "api_error"
            _LOGGER.warning(
                "[config_flow] Stop search HTTP error (query=%s, status=%s)",
                name,
                ex.status,
            )
    except aiohttp.ClientConnectorError as ex:
        error_key = "api_unreachable"
        _LOGGER.warning("[config_flow] Stop search connection error (query=%s): %s", name, ex)
    except aiohttp.ServerDisconnectedError as ex:
        error_key = "api_disconnected"
        _LOGGER.warning("[config_flow] Stop search server disconnected (query=%s): %s", name, ex)
    except aiohttp.ClientError as ex:
        error_key = "api_error"
        _LOGGER.warning("[config_flow] Stop search client error (query=%s): %s", name, ex)
    except TimeoutError as ex:
        error_key = "api_timeout"
        _LOGGER.warning("[config_flow] Stop search timeout (query=%s): %s", name, ex)
    except Exception as ex:  # pylint: disable=broad-exception-caught
        error_key = "api_unexpected_error"
        _LOGGER.exception(
            "[config_flow] Unexpected error while searching stop IDs (query=%s): %s", name, ex
        )

    # If there was an error, return early
    if error_key is not None:
        return False, [], error_key

    if not isinstance(stops, list):
        _LOGGER.warning(
            "[config_flow] API returned unexpected stop search payload type for query '%s'", name
        )
        return True, [], None

    # Convert API data into our format
    result = [
        {CONF_DEPARTURES_NAME: stop["name"], CONF_DEPARTURES_STOP_ID: stop["id"]}
        for stop in stops
        if stop["type"] == "stop"
    ]
    
    _LOGGER.debug("[config_flow] Found %s stops for query '%s'", len(result), name)
    return True, result, None


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


class TransportConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Init the ConfigFlow."""
        self.data: dict[str, Any] = {}

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
        return self.async_create_entry(
            title=f"{data[CONF_DEPARTURES_NAME]} [{data[CONF_DEPARTURES_STOP_ID]}]",
            data=data,
        )
