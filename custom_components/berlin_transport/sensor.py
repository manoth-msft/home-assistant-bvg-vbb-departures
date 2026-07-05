# mypy: disable-error-code="attr-defined"

"""The Berlin (BVG) and Brandenburg (VBB) transport integration."""
from __future__ import annotations

import logging
from typing import Any, Mapping
from datetime import datetime, timedelta

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import PLATFORM_SCHEMA

from .const import (  # pylint: disable=unused-import
    DOMAIN,  # noqa
    SCAN_INTERVAL,  # noqa
    FALLBACK_TIME,
    API_ENDPOINT,
    API_MAX_RESULTS,
    CONF_DEPARTURES,
    CONF_DEPARTURES_DIRECTION,
    CONF_DEPARTURES_EXCLUDED_STOPS,
    CONF_DEPARTURES_DURATION,
    CONF_DEPARTURES_STOP_ID,
    CONF_DEPARTURES_WALKING_TIME,
    CONF_EXCLUDE_RINGBAHN_CLOCKWISE,
    CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE,
    CONF_REMOVE_BERLIN_SUFFIX,
    CONF_SHOW_API_LINE_COLORS,
    CONF_TYPE_BUS,
    CONF_TYPE_EXPRESS,
    CONF_TYPE_FERRY,
    CONF_TYPE_REGIONAL,
    CONF_TYPE_SUBURBAN,
    CONF_TYPE_SUBWAY,
    CONF_TYPE_TRAM,
    CONF_DEPARTURES_NAME,
    DEFAULT_ICON,
    STOP_SUFFIX_BERLIN,
)
from .departure import Departure

_LOGGER = logging.getLogger(__name__)

TRANSPORT_TYPES_SCHEMA = {
    vol.Optional(CONF_TYPE_SUBURBAN, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_SUBWAY, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_TRAM, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_BUS, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_FERRY, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_EXPRESS, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_REGIONAL, default=True): cv.boolean,
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DEPARTURES): [
            {
                vol.Required(CONF_DEPARTURES_NAME): cv.string,
                vol.Required(CONF_DEPARTURES_STOP_ID): cv.positive_int,
                vol.Optional(CONF_DEPARTURES_DIRECTION): cv.string,
                vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): cv.string,
                vol.Optional(CONF_DEPARTURES_DURATION): cv.positive_int,
                vol.Optional(CONF_DEPARTURES_WALKING_TIME, default=1): cv.positive_int,
                vol.Optional(CONF_SHOW_API_LINE_COLORS, default=False): cv.boolean,
                vol.Optional(CONF_EXCLUDE_RINGBAHN_CLOCKWISE, default=False): cv.boolean,
                vol.Optional(CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE, default=False): cv.boolean,
                vol.Optional(CONF_REMOVE_BERLIN_SUFFIX, default=False): cv.boolean,
                **TRANSPORT_TYPES_SCHEMA,
            }
        ]
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    if CONF_DEPARTURES in config:
        for departure in config[CONF_DEPARTURES]:
            async_add_entities([TransportSensor(hass, departure)], True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([TransportSensor(hass, config_entry.data, config_entry.entry_id)], True)


class TransportSensor(SensorEntity):
    departures: list[Departure] = []

    def __init__(
        self,
        hass: HomeAssistant,
        config: Mapping[str, Any],
        entry_id: str | None = None,
    ) -> None:
        self.hass: HomeAssistant = hass
        self.config = config
        self._entry_id = entry_id
        self.stop_id: int = config[CONF_DEPARTURES_STOP_ID]
        self.excluded_stops: str | None = config.get(CONF_DEPARTURES_EXCLUDED_STOPS)
        self.sensor_name: str | None = config.get(CONF_DEPARTURES_NAME)
        self.direction: str | None = config.get(CONF_DEPARTURES_DIRECTION)
        self.duration: int | None = config.get(CONF_DEPARTURES_DURATION)
        self.walking_time: int = config.get(CONF_DEPARTURES_WALKING_TIME) or 1
        # we add +1 minute anyway to delete the "just gone" transport
        self.exclude_ringbahn_clockwise: bool = config.get(CONF_EXCLUDE_RINGBAHN_CLOCKWISE) or False
        self.exclude_ringbahn_counterclockwise: bool = (
            config.get(CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE) or False
        )
        self.remove_berlin_suffix: bool = config.get(CONF_REMOVE_BERLIN_SUFFIX) or False
        self.show_api_line_colors: bool = config.get(CONF_SHOW_API_LINE_COLORS) or False
        self.session = async_get_clientsession(hass)
        self.departures = []
        self.last_update_success: datetime | None = None
        self._consecutive_failures = 0
        self._next_retry_at: datetime | None = None
        self._attr_available: bool = True

    def _is_within_fallback(self, now_utc: datetime) -> bool:
        return bool(
            self.last_update_success
            and (now_utc - self.last_update_success) <= FALLBACK_TIME
        )

    def _prune_cached_departures(self) -> None:
        self.departures = [
            departure
            for departure in self.departures
            if departure.timestamp >= datetime.now(departure.timestamp.tzinfo)
        ]

    @property
    def name(self) -> str:
        name = self.sensor_name or f"Stop ID: {self.stop_id}"
        if self.remove_berlin_suffix and name:
            name = name.replace(STOP_SUFFIX_BERLIN, "").strip()
        return name
    
    @property
    def icon(self) -> str:
        next_departure = self.next_departure()
        if next_departure:
            return next_departure.icon
        return DEFAULT_ICON

    @property
    def unique_id(self) -> str:
        return self._entry_id or f"stop_{self.stop_id}_{self.sensor_name}_departures"

    @property
    def native_value(self) -> str:
        next_departure = self.next_departure()
        if next_departure:
            return f"Next {next_departure.line_name} at {next_departure.time}"
        return "N/A"

    @property
    def extra_state_attributes(self):
        now_utc = datetime.utcnow()
        cache_age_seconds = None
        if self.last_update_success:
            cache_age_seconds = int((now_utc - self.last_update_success).total_seconds())

        return {
            "departures": [
                departure.to_dict(self.show_api_line_colors, self.walking_time)
                for departure in self.departures or []
            ],
            "last_update_success": self.last_update_success,
            "cache_age_seconds": cache_age_seconds,
            "consecutive_failures": self._consecutive_failures,
            "backoff_until": self._next_retry_at,
        }

    async def async_update(self):
        now_utc = datetime.utcnow()
        if self._next_retry_at is not None and now_utc < self._next_retry_at:
            self._prune_cached_departures()
            if self._consecutive_failures > 0:
                if not self._is_within_fallback(now_utc) or not self.departures:
                    self._attr_available = False
                    self.departures = []
            _LOGGER.debug("Skipping API request for stop %s due to backoff until %s", self.stop_id, self._next_retry_at)
            return

        departures = await self.fetch_departures()
        if departures is None:
            self._consecutive_failures += 1
            backoff_seconds = min(900, SCAN_INTERVAL.total_seconds() * (2 ** (self._consecutive_failures - 1)))
            self._next_retry_at = now_utc + timedelta(seconds=backoff_seconds)

            self._prune_cached_departures()
            if self._is_within_fallback(now_utc) and self.departures:
                self._attr_available = True
                _LOGGER.warning(
                    "Using cached departures for stop %s after API failure (%s consecutive failures)",
                    self.stop_id,
                    self._consecutive_failures,
                )
            else:
                self._attr_available = False
                _LOGGER.warning(
                    "Dropping stale cache for stop %s after API failure (%s consecutive failures)",
                    self.stop_id,
                    self._consecutive_failures,
                )
                self.departures = []
            return

        self._consecutive_failures = 0
        self._next_retry_at = None
        self.last_update_success = now_utc
        self._attr_available = True
        self.departures = departures

    async def fetch_directional_departure(self, direction: str | None) -> list[Departure] | None:
        try:
            params: dict[str, Any] = {
                "when": (datetime.utcnow() + timedelta(minutes=self.walking_time)).isoformat(),
                "results": API_MAX_RESULTS,
                "suburban": self.config.get(CONF_TYPE_SUBURBAN) or False,
                "subway": self.config.get(CONF_TYPE_SUBWAY) or False,
                "tram": self.config.get(CONF_TYPE_TRAM) or False,
                "bus": self.config.get(CONF_TYPE_BUS) or False,
                "ferry": self.config.get(CONF_TYPE_FERRY) or False,
                "express": self.config.get(CONF_TYPE_EXPRESS) or False,
                "regional": self.config.get(CONF_TYPE_REGIONAL) or False,
            }
            if self.duration is not None:
                params["duration"] = self.duration
            if direction is not None:
                params["direction"] = direction

            async with async_timeout.timeout(30):
                response = await self.session.get(
                    url=f"{API_ENDPOINT}/stops/{self.stop_id}/departures",
                    params=params,
                )
                response.raise_for_status()
                departures = await response.json()
        except aiohttp.ClientResponseError as ex:
            if ex.status == 429:
                retry_after = ex.headers.get("Retry-After") if ex.headers else None
                _LOGGER.warning(
                    "API rate limited for stop %s (status=%s, retry_after=%s)",
                    self.stop_id,
                    ex.status,
                    retry_after,
                )
            else:
                _LOGGER.warning(
                    "API HTTP error for stop %s (status=%s, message=%s)",
                    self.stop_id,
                    ex.status,
                    ex.message,
                )
            return None
        except aiohttp.ClientConnectorError as ex:
            _LOGGER.warning("API connection error for stop %s: %s", self.stop_id, ex)
            return None
        except aiohttp.ServerDisconnectedError as ex:
            _LOGGER.warning("API server disconnected for stop %s: %s", self.stop_id, ex)
            return None
        except aiohttp.ClientError as ex:
            _LOGGER.warning("API client error for stop %s: %s", self.stop_id, ex)
            return None
        except TimeoutError as ex:
            _LOGGER.warning("API timeout for stop %s: %s", self.stop_id, ex)
            return None
        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("Unexpected API error for stop %s: %s", self.stop_id, ex)
            return None

        _LOGGER.debug("OK: departures response for stop %s (status=%s)", self.stop_id, response.status)

        departures_data = departures.get("departures") or []
        if not isinstance(departures_data, list):
            _LOGGER.warning("API response for stop %s has unexpected departures format", self.stop_id)
            return None

        if self.excluded_stops is None:
            excluded_stops = []
        else:
            excluded_stops = [stop.strip() for stop in self.excluded_stops.split(",") if stop.strip()]

        parsed_departures: list[Departure] = []
        for departure in departures_data:
            if departure.get("stop", {}).get("id") in excluded_stops:
                continue
            try:
                parsed_departures.append(Departure.from_dict(departure))
            except (KeyError, TypeError, ValueError) as ex:
                _LOGGER.debug("Skipping malformed departure for stop %s: %s", self.stop_id, ex)

        return parsed_departures

    async def fetch_departures(self) -> list[Departure] | None:
        departures = []

        # Step 1: Fetch departures
        
        if self.direction is None:
            res = await self.fetch_directional_departure(self.direction)
            if res is None:
                return None
            departures += res
        else:
            for direction in self.direction.split(','):
                res = await self.fetch_directional_departure(direction.strip())
                if res is None:
                    return None
                departures += res
       
        # Step 2: Deduplicate departures
            # Duplicates should only exist for the Ringbahn and filtering for both directions

        deduplicated_departures = set(departures)

        # Step 3: Apply Ringbahn filter
            # The API response includes the symbols ⟲ and ⟳ as part of the direction value,
            # e.g. "direction": "Ringbahn S42 ⟲"
            # We filter for just these chars, instead of hard-coding the full string
            # (e.g. "Ringbahn S42 ⟲" / "Ringbahn S41 ⟳"). This may be more future-proof.
        
        filtered_departures = [
            d for d in deduplicated_departures
            if not (
                (self.exclude_ringbahn_clockwise and d.direction and "⟳" in d.direction) or
                (self.exclude_ringbahn_counterclockwise and d.direction and "⟲" in d.direction)
            )
        ]

        # Step 4: Clean direction suffix if enabled
        if self.remove_berlin_suffix:
            for d in filtered_departures:
                if d.direction:
                    d.direction = d.direction.replace(STOP_SUFFIX_BERLIN, "").strip()

        # Step 5: Return result
            # Return filtered result, ordered by timestamp
        
        return sorted(filtered_departures, key=lambda d: d.timestamp)

    def next_departure(self):
        if self.departures and isinstance(self.departures, list):
            return self.departures[0]
        return None
