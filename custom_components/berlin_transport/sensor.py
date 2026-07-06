# mypy: disable-error-code="attr-defined"

"""The Berlin (BVG) and Brandenburg (VBB) transport integration."""
from __future__ import annotations

import logging
import copy
from typing import Any, Mapping
from datetime import datetime, timedelta, timezone

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
    BVG_FALLBACK_ENABLED,
    DEFAULT_DEPARTURES_DURATION,
    CONF_DEPARTURES,
    CONF_DEPARTURES_DIRECTION,
    CONF_DEPARTURES_EXCLUDED_STOPS,
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
from .bvg_api import fetch_bvg_departures
from .bvg_departure import parse_bvg_departures

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
    def __init__(
        self,
        hass: HomeAssistant,
        config: Mapping[str, Any],
        entry_id: str | None = None,
    ) -> None:
        self.hass: HomeAssistant = hass
        self.config = config
        self.stop_id: int = config[CONF_DEPARTURES_STOP_ID]
        self.excluded_stops: str | None = config.get(CONF_DEPARTURES_EXCLUDED_STOPS)
        self.sensor_name: str | None = config.get(CONF_DEPARTURES_NAME)
        self.direction: str | None = config.get(CONF_DEPARTURES_DIRECTION)
        self.duration: int = DEFAULT_DEPARTURES_DURATION
        self.walking_time: int = config.get(CONF_DEPARTURES_WALKING_TIME) or 1
        # we add +1 minute anyway to delete the "just gone" transport
        self.exclude_ringbahn_clockwise: bool = config.get(CONF_EXCLUDE_RINGBAHN_CLOCKWISE) or False
        self.exclude_ringbahn_counterclockwise: bool = (
            config.get(CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE) or False
        )
        self.remove_berlin_suffix: bool = config.get(CONF_REMOVE_BERLIN_SUFFIX) or False
        self.show_api_line_colors: bool = config.get(CONF_SHOW_API_LINE_COLORS) or False
        self.session = async_get_clientsession(hass)
        # Instance-level caches (not shared between sensor instances)
        self.departures: list[Departure] = []
        self._etag_by_request: dict[str, str] = {}
        self._cached_departures_by_request: dict[str, list[Departure]] = {}
        self.last_update_success: datetime | None = None
        self._consecutive_failures = 0
        self._next_retry_at: datetime | None = None
        self._attr_available: bool = True
        self._data_source: str = "transport.rest"  # Track which API provided current data
        self._using_fallback: bool = False  # True when in fallback mode (backoff active)
        # Request cache tracking to prevent unbounded memory growth
        self._cache_request_keys: set[str] = set()  # Track all request keys for cleanup

    def _is_within_fallback(self, now_utc: datetime) -> bool:
        return bool(
            self.last_update_success
            and (now_utc - self.last_update_success) <= FALLBACK_TIME
        )

    def _is_data_stale(self, now_utc: datetime) -> bool:
        return bool(
            self.departures
            and self.last_update_success
            and (now_utc - self.last_update_success) > FALLBACK_TIME
        )

    def _last_updated_ago(self, now_utc: datetime) -> str | None:
        if self.last_update_success is None:
            return None

        age_seconds = int((now_utc - self.last_update_success).total_seconds())
        if age_seconds < 60:
            return "gerade eben"

        minutes = max(1, age_seconds // 60)
        return f"vor {minutes} Minuten"

    def _health_status(self, now_utc: datetime) -> str:
        if self._next_retry_at is not None and now_utc < self._next_retry_at:
            return "backoff"

        if not self.departures and self.last_update_success is None:
            return "no_data"

        if self._is_data_stale(now_utc):
            return "stale"

        if self._consecutive_failures > 0:
            return "degraded"

        return "ok"

    def _health_details(self, now_utc: datetime) -> str:
        if self._next_retry_at is not None and now_utc < self._next_retry_at:
            return f"Retry erst ab {self._next_retry_at.isoformat()}"

        if not self.departures and self.last_update_success is None:
            return "Noch keine erfolgreichen API-Daten"

        if self._is_data_stale(now_utc):
            return "Cache ist älter als der Fallback-Zeitraum"

        if self._consecutive_failures > 0:
            return f"{self._consecutive_failures} aufeinanderfolgende Fehler"

        return "Daten sind aktuell"

    def _request_variant_key(self, direction: str | None) -> str:
        direction_key = direction or "*"
        excluded_stops_key = self.excluded_stops or ""
        return "|".join(
            [
                str(self.stop_id),
                direction_key,
                str(self.duration),
                str(self.walking_time),
                str(bool(self.config.get(CONF_TYPE_SUBURBAN))),
                str(bool(self.config.get(CONF_TYPE_SUBWAY))),
                str(bool(self.config.get(CONF_TYPE_TRAM))),
                str(bool(self.config.get(CONF_TYPE_BUS))),
                str(bool(self.config.get(CONF_TYPE_FERRY))),
                str(bool(self.config.get(CONF_TYPE_EXPRESS))),
                str(bool(self.config.get(CONF_TYPE_REGIONAL))),
                excluded_stops_key,
            ]
        )

    def _prune_cached_departures(self) -> None:
        now_utc = datetime.now(timezone.utc)
        self.departures = [
            departure
            for departure in self.departures
            if departure.timestamp >= now_utc
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
        # Use consistent format for backward compatibility (0.1.3 -> 0.1.4+ upgrades)
        # Do NOT use entry_id as it changes unique_id between versions and causes sensor recreation
        return f"stop_{self.stop_id}_{self.sensor_name}_departures"

    @property
    def native_value(self) -> str:
        next_departure = self.next_departure()
        if next_departure:
            return f"Next {next_departure.line_name} at {next_departure.time}"
        return "N/A"

    @property
    def extra_state_attributes(self):
        now_utc = datetime.now(timezone.utc)
        self._prune_cached_departures()
        cache_age_seconds = None
        if self.last_update_success:
            cache_age_seconds = int((now_utc - self.last_update_success).total_seconds())

        return {
            "departures": [
                departure.to_dict(self.show_api_line_colors, self.walking_time)
                for departure in self.departures or []
            ],
            "data_source": self._data_source,
            "last_update_success": self.last_update_success,
            "last_updated": self.last_update_success,
            "last_updated_ago": self._last_updated_ago(now_utc),
            "health_status": self._health_status(now_utc),
            "health_details": self._health_details(now_utc),
            "cache_age_seconds": cache_age_seconds,
            "data_is_stale": self._is_data_stale(now_utc),
            "consecutive_failures": self._consecutive_failures,
            "backoff_until": self._next_retry_at,
        }

    async def async_update(self):
        now_utc = datetime.now(timezone.utc)
        
        # Backoff active: try only BVG fallback API if enabled, don't try transport.rest yet
        if self._next_retry_at is not None and now_utc < self._next_retry_at:
            self._attr_available = bool(self.departures)
            
            if BVG_FALLBACK_ENABLED:
                _LOGGER.debug(
                    "[BACKOFF] Stop %s in backoff until %s, attempting BVG API only",
                    self.stop_id,
                    self._next_retry_at,
                )
                
                # Try BVG fallback during backoff
                departures = await self._fetch_bvg_fallback()
                if departures is not None:
                    # BVG fallback successful during backoff
                    self._consecutive_failures = 0
                    self.last_update_success = now_utc
                    self._data_source = "bvg_api"
                    self._attr_available = True
                    self.departures = departures
                    _LOGGER.info(
                        "[BACKOFF] BVG API provided departures for stop %s during backoff",
                        self.stop_id,
                    )
                    return
                
                # BVG fallback also failed, use cache
                if self.departures:
                    _LOGGER.debug(
                        "[BACKOFF] BVG API also failed for stop %s, using cached departures",
                        self.stop_id,
                    )
            else:
                _LOGGER.debug(
                    "Skipping API request for stop %s due to backoff until %s",
                    self.stop_id,
                    self._next_retry_at,
                )
            return

        # Backoff finished: reset fallback flag and try transport.rest again
        if self._using_fallback:
            self._using_fallback = False
            _LOGGER.info(
                "[BACKOFF] Backoff expired for stop %s, switching back to transport.rest",
                self.stop_id,
            )

        departures = await self.fetch_departures()
        if departures is None:
            self._consecutive_failures += 1
            backoff_seconds = min(
                900,
                SCAN_INTERVAL.total_seconds()
                * (2 ** (self._consecutive_failures - 1)),
            )
            self._next_retry_at = now_utc + timedelta(seconds=backoff_seconds)
            self._using_fallback = True

            self._attr_available = bool(self.departures)
            if self.departures:
                if self._is_within_fallback(now_utc):
                    _LOGGER.warning(
                        "Using cached departures for stop %s after API failure "
                        "(%s consecutive failures)",
                        self.stop_id,
                        self._consecutive_failures,
                    )
                else:
                    _LOGGER.warning(
                        "Using stale cached departures for stop %s after API failure "
                        "(%s consecutive failures)",
                        self.stop_id,
                        self._consecutive_failures,
                    )
            else:
                _LOGGER.warning(
                    "No cached departures available for stop %s after API failure "
                    "(%s consecutive failures)",
                    self.stop_id,
                    self._consecutive_failures,
                )
            return

        self._consecutive_failures = 0
        self._next_retry_at = None
        self._using_fallback = False
        self.last_update_success = now_utc
        self._data_source = "transport.rest"
        self._attr_available = True
        self.departures = departures

    def _log_departure_fetch_error(self, ex: Exception) -> None:
        if isinstance(ex, aiohttp.ClientResponseError):
            if ex.status == 429:
                retry_after = ex.headers.get("Retry-After") if ex.headers else None
                _LOGGER.warning(
                    "API rate limited for stop %s (status=%s, retry_after=%s)",
                    self.stop_id,
                    ex.status,
                    retry_after,
                )
                return
            _LOGGER.warning(
                "API HTTP error for stop %s (status=%s, message=%s)",
                self.stop_id,
                ex.status,
                ex.message,
            )
            return

        if isinstance(ex, aiohttp.ClientConnectorError):
            _LOGGER.warning("API connection error for stop %s: %s", self.stop_id, ex)
            return

        if isinstance(ex, aiohttp.ServerDisconnectedError):
            _LOGGER.warning("API server disconnected for stop %s: %s", self.stop_id, ex)
            return

        if isinstance(ex, aiohttp.ClientError):
            _LOGGER.warning("API client error for stop %s: %s", self.stop_id, ex)
            return

        if isinstance(ex, TimeoutError):
            _LOGGER.warning("API timeout for stop %s: %s", self.stop_id, ex)
            return

        _LOGGER.exception("Unexpected API error for stop %s: %s", self.stop_id, ex)

    async def _fetch_bvg_fallback(self) -> list[Departure] | None:
        """Fallback to BVG API when transport.rest fails.

        Note: BVG API only covers Berlin. For VBB stops outside Berlin, this fallback
        will not work. In such cases, the sensor will continue with cached data or
        report no_data if no cache is available.

        Returns:
            List of Departure objects from BVG API or None on error.
        """
        if not self.sensor_name:
            _LOGGER.warning(
                "Cannot use BVG fallback for stop %s (no sensor_name)",
                self.stop_id,
            )
            return None

        _LOGGER.debug(
            "[FALLBACK] Attempting BVG API for stop '%s' (stop_id=%s)",
            self.sensor_name,
            self.stop_id,
        )

        bvg_response = await fetch_bvg_departures(
            session=self.session,
            stop_name=self.sensor_name,
            max_journeys=API_MAX_RESULTS,
        )

        if bvg_response is None:
            _LOGGER.warning(
                "[FALLBACK] BVG API request failed for stop '%s' (stop_id=%s). "
                "Note: BVG API only covers Berlin; this is expected for VBB stops outside Berlin.",
                self.sensor_name,
                self.stop_id,
            )
            return None

        try:
            parsed_departures = parse_bvg_departures(
                response=bvg_response,
            )

            if not parsed_departures:
                _LOGGER.warning(
                    "[FALLBACK] BVG API returned empty response for stop '%s' (stop_id=%s). "
                    "This may indicate the stop is not covered by BVG API (only covers Berlin).",
                    self.sensor_name,
                    self.stop_id,
                )
                return None

            self._data_source = "bvg_api"  # Mark that we're using fallback source
            _LOGGER.info(
                "[FALLBACK] SUCCESS for stop '%s' (stop_id=%s): got %s departures from BVG API "
                "(note: limited data - no warnings or vehicle cancellations)",
                self.sensor_name,
                self.stop_id,
                len(parsed_departures),
            )

            return parsed_departures

        except (KeyError, TypeError, ValueError) as ex:
            _LOGGER.exception(
                "[FALLBACK] BVG API parsing error for stop '%s' (stop_id=%s): %s",
                self.sensor_name,
                self.stop_id,
                ex,
            )
            return None

    async def fetch_directional_departure(self, direction: str | None) -> list[Departure] | None:
        departures: dict[str, Any] = {}
        request_headers: dict[str, str] = {}
        request_key = self._request_variant_key(direction)
        known_etag = self._etag_by_request.get(request_key)
        if known_etag:
            request_headers["If-None-Match"] = known_etag
            _LOGGER.debug(
                "Sending conditional request for stop %s (key=%s) with If-None-Match=%s",
                self.stop_id,
                request_key,
                known_etag,
            )

        try:
            params: dict[str, Any] = {
                "when": (
                    datetime.utcnow() + timedelta(minutes=self.walking_time)
                ).isoformat(),
                "results": API_MAX_RESULTS,
                "suburban": str(bool(self.config.get(CONF_TYPE_SUBURBAN))).lower(),
                "subway": str(bool(self.config.get(CONF_TYPE_SUBWAY))).lower(),
                "tram": str(bool(self.config.get(CONF_TYPE_TRAM))).lower(),
                "bus": str(bool(self.config.get(CONF_TYPE_BUS))).lower(),
                "ferry": str(bool(self.config.get(CONF_TYPE_FERRY))).lower(),
                "express": str(bool(self.config.get(CONF_TYPE_EXPRESS))).lower(),
                "regional": str(bool(self.config.get(CONF_TYPE_REGIONAL))).lower(),
            }
            params["duration"] = self.duration
            if direction is not None:
                params["direction"] = direction

            async with async_timeout.timeout(240):
                response = await self.session.get(
                    url=f"{API_ENDPOINT}/stops/{self.stop_id}/departures",
                    params=params,
                    headers=request_headers,
                )

                if response.status == 304:
                    cached_departures = self._cached_departures_by_request.get(request_key)
                    if cached_departures is not None:
                        _LOGGER.debug(
                            "ETag cache hit for stop %s (key=%s, 304 Not Modified), "
                            "reusing %s cached departures",
                            self.stop_id,
                            request_key,
                            len(cached_departures),
                        )
                        return copy.deepcopy(cached_departures)

                    _LOGGER.warning(
                        "Received 304 Not Modified for stop %s (key=%s) "
                        "without cached departures",
                        self.stop_id,
                        request_key,
                    )
                    return None

                response.raise_for_status()
                departures = await response.json()
        except (
            aiohttp.ClientError,
            TimeoutError,
        ) as ex:
            self._log_departure_fetch_error(ex)
            return None

        _LOGGER.debug(
            "OK: departures response for stop %s (status=%s)",
            self.stop_id,
            response.status,
        )

        departures_data = departures.get("departures") or []
        if not isinstance(departures_data, list):
            _LOGGER.warning(
                "API response for stop %s has unexpected departures format",
                self.stop_id,
            )
            return None

        if self.excluded_stops is None:
            excluded_stops = []
        else:
            excluded_stops = [
                stop.strip()
                for stop in self.excluded_stops.split(",")
                if stop.strip()
            ]

        parsed_departures: list[Departure] = []
        for departure in departures_data:
            if departure.get("stop", {}).get("id") in excluded_stops:
                continue
            try:
                parsed_departures.append(Departure.from_dict(departure))
            except (KeyError, TypeError, ValueError) as ex:
                _LOGGER.debug("Skipping malformed departure for stop %s: %s", self.stop_id, ex)

        response_etag = response.headers.get("ETag")
        if response_etag:
            self._etag_by_request[request_key] = response_etag
            self._cached_departures_by_request[request_key] = copy.deepcopy(
                parsed_departures
            )
            # Track request key and clean up old cache entries to prevent memory leak
            if request_key not in self._cache_request_keys:
                self._cache_request_keys.add(request_key)
                # Keep only the 10 most recent request keys to prevent unbounded memory growth
                if len(self._cache_request_keys) > 10:
                    oldest_key = next(iter(self._cache_request_keys))
                    self._cache_request_keys.discard(oldest_key)
                    self._etag_by_request.pop(oldest_key, None)
                    self._cached_departures_by_request.pop(oldest_key, None)
                    _LOGGER.debug(
                        "Removed old cache entry for stop %s (key=%s) to prevent memory leak",
                        self.stop_id,
                        oldest_key,
                    )
            _LOGGER.debug(
                "Stored ETag for stop %s (key=%s): %s (cached %s departures)",
                self.stop_id,
                request_key,
                response_etag,
                len(parsed_departures),
            )

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
            for direction in self.direction.split(","):
                res = await self.fetch_directional_departure(direction.strip())
                if res is None:
                    return None
                departures += res

        # Step 2: Deduplicate departures
        # Duplicates should only exist for the Ringbahn and filtering for both directions.

        deduplicated_departures = set(departures)

        # Step 3: Apply Ringbahn filter
        # The API response includes the symbols ⟲ and ⟳ as part of direction value.
        # We filter using these symbols to avoid hard-coding route names.

        filtered_departures = [
            d
            for d in deduplicated_departures
            if not (
                (self.exclude_ringbahn_clockwise and d.direction and "⟳" in d.direction)
                or (
                    self.exclude_ringbahn_counterclockwise
                    and d.direction
                    and "⟲" in d.direction
                )
            )
        ]

        # Step 4: Clean direction suffix if enabled
        if self.remove_berlin_suffix:
            for d in filtered_departures:
                if d.direction:
                    d.direction = d.direction.replace(STOP_SUFFIX_BERLIN, "").strip()

        # Step 5: Return result
        # Return filtered result, ordered by timestamp.

        return sorted(filtered_departures, key=lambda d: d.timestamp)

    def next_departure(self):
        if self.departures and isinstance(self.departures, list):
            return self.departures[0]
        return None
