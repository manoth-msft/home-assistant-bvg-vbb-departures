# mypy: disable-error-code="attr-defined"

"""The Berlin (BVG) and Brandenburg (VBB) transport integration."""

from __future__ import annotations

import asyncio
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
    API_REQUEST_TIMEOUT,
    API_USER_AGENT,
    EXTRACT_AND_STORE_DIRECTION_NAME,
    BVG_FALLBACK_ENABLED,
    DEFAULT_DEPARTURES_DURATION,
    DEFAULT_ICON,
    DEFAULT_WALKING_TIME,
    BACKOFF_BASE,
    BACKOFF_MAX_SECONDS,
    CACHE_TTL_SECONDS,
    CONF_DEPARTURES,
    CONF_DEPARTURES_DIRECTION,
    CONF_DEPARTURES_DIRECTION_NAME,
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
    STOP_SUFFIX_BERLIN,
)
from .departure import Departure
from .bvg_api import fetch_and_parse_bvg_departures

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
                vol.Optional(CONF_DEPARTURES_DIRECTION_NAME): cv.string,  # v0.1.5: set by backfill
                vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): cv.string,
                vol.Optional(CONF_DEPARTURES_WALKING_TIME, default=1): cv.positive_int,
                vol.Optional(CONF_SHOW_API_LINE_COLORS, default=False): cv.boolean,
                vol.Optional(
                    CONF_EXCLUDE_RINGBAHN_CLOCKWISE, default=False
                ): cv.boolean,
                vol.Optional(
                    CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE, default=False
                ): cv.boolean,
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
    async_add_entities(
        [TransportSensor(hass, config_entry.data, config_entry.entry_id)], True
    )


class TransportSensor(SensorEntity):
    """Home Assistant sensor entity for displaying VBB/BVG departures.
    
    This sensor fetches real-time departure information from VBB
    transport.rest API with automatic fallback to BVG API during
    connectivity issues. It supports:
    - Multiple directions separated by commas
    - Automatic deduplication of Ringbahn departures
    - ETag-based HTTP caching to reduce API calls
    - Exponential backoff for resilient error recovery
    - Configurable filtering (Ringbahn directions, Berlin suffix removal)
    - Timezone-aware datetime handling (UTC)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: Mapping[str, Any],
        entry_id: str | None = None,  # pylint: disable=unused-argument
    ) -> None:
        """Initialize TransportSensor with configuration from Home Assistant.
        
        Args:
            hass: Home Assistant instance for session management and callbacks
            config: Configuration dictionary containing stop_id, sensor_name, direction, etc.
            entry_id: Config entry ID (unused, kept for compatibility)
        """
        self.hass: HomeAssistant = hass
        self.config = config
        self.stop_id: int = config[CONF_DEPARTURES_STOP_ID]
        self.excluded_stops: str | None = config.get(CONF_DEPARTURES_EXCLUDED_STOPS)
        self.sensor_name: str | None = config.get(CONF_DEPARTURES_NAME)
        self.direction: str | None = config.get(CONF_DEPARTURES_DIRECTION)
        self.direction_name: str | None = config.get(
            CONF_DEPARTURES_DIRECTION_NAME
        )  # v0.1.5: direction text for BVG filtering
        self.duration: int = DEFAULT_DEPARTURES_DURATION
        self.walking_time: int = config.get(CONF_DEPARTURES_WALKING_TIME) or DEFAULT_WALKING_TIME
        # we add +1 minute anyway to delete the "just gone" transport
        self.exclude_ringbahn_clockwise: bool = (
            config.get(CONF_EXCLUDE_RINGBAHN_CLOCKWISE) or False
        )
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
        self._data_source: str = (
            "transport.rest"  # Track which API provided current data
        )
        self._using_fallback: bool = (
            False  # True when in fallback mode (backoff active)
        )
        # Request cache tracking with timestamps for TTL-based cleanup
        self._cache_request_keys: dict[str, datetime] = {}  # Key → last updated timestamp
        # Lock for thread-safe state updates
        self._update_lock = asyncio.Lock()
        # Attribute caching to reduce unnecessary regeneration
        self._cached_attributes: dict[str, Any] | None = None
        self._attributes_cache_time: datetime | None = None

    def _get_now_utc(self) -> datetime:
        """Get current time in UTC (always timezone-aware).
        
        This helper ensures all datetime comparisons work with UTC-aware objects.
        Using this method prevents timezone bugs that could arise from accidentally
        mixing naive and aware datetime objects.
        
        Returns:
            Current UTC time as a timezone-aware datetime object.
        """
        return datetime.now(timezone.utc)

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
        now_utc = self._get_now_utc()
        self.departures = [
            departure for departure in self.departures if departure.timestamp >= now_utc
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
            return next_departure.icon or DEFAULT_ICON
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

    def _invalidate_attributes_cache(self) -> None:
        """Invalidate cached attributes when sensor data changes.
        
        This should be called whenever departures or state is updated to ensure
        that the next read of extra_state_attributes regenerates with fresh data.
        """
        self._cached_attributes = None

    def _refresh_attributes_cache(self) -> dict[str, Any]:
        """Regenerate attributes cache if stale (>5 seconds old).
        
        Home Assistant reads extra_state_attributes multiple times per update cycle
        (state machine, templates, history, UI). This method caches the result to
        avoid redundant computation of:
        - Departure dict conversions (expensive to_dict() calls)
        - Health status calculations
        - Time-based calculations
        
        The cache is invalidated when async_update() completes and regenerated on
        next property read if >5 seconds old.
        
        Returns:
            Dictionary of state attributes ready for Home Assistant.
        """
        now_utc = self._get_now_utc()
        
        # Return cached attributes if still fresh (<5 seconds old)
        if self._cached_attributes is not None and self._attributes_cache_time is not None:
            age_seconds = (now_utc - self._attributes_cache_time).total_seconds()
            if age_seconds < 5:
                return self._cached_attributes
        
        # Regenerate cache
        self._prune_cached_departures()
        cache_age_seconds = None
        if self.last_update_success:
            cache_age_seconds = int(
                (now_utc - self.last_update_success).total_seconds()
            )

        self._cached_attributes = {
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
        self._attributes_cache_time = now_utc
        return self._cached_attributes

    @property
    def extra_state_attributes(self):
        """Return cached state attributes (regenerated if >5 seconds old).
        
        Uses caching to avoid redundant computation when Home Assistant reads
        this property multiple times per update cycle. Attributes are invalidated
        when async_update() completes and regenerated on next access if needed.
        """
        return self._refresh_attributes_cache()

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity is removed from Home Assistant.
        
        This hook ensures proper cleanup when the sensor is removed.
        The aiohttp session is managed by Home Assistant and will be
        closed automatically, so no explicit cleanup is needed here.
        """

    async def async_update(self) -> None:
        """Poll for departure updates from VBB/BVG APIs.
        
        This is the main update method called by Home Assistant's coordinator on
        SCAN_INTERVAL (120 seconds). It orchestrates the complete update cycle:
        
        1. Check if currently in exponential backoff (after API failures)
        2. Fetch departures from VBB transport.rest API (with ETag caching)
        3. Fall back to BVG API if transport.rest fails
        4. Parse and deduplicate results
        5. Apply filters and sort by departure time
        6. Update sensor state attributes
        
        All state modifications are protected by asyncio.Lock to prevent race conditions
        when concurrent updates occur (e.g., manual refresh + scheduled update).
        
        On success: Sets self.departures, resets failure counter, updates last_update_success
        On failure: Increments failure counter, activates exponential backoff
        """
        async with self._update_lock:
            now_utc = self._get_now_utc()

            # Check if we're in backoff period
            if self._next_retry_at is not None and now_utc < self._next_retry_at:
                await self._handle_backoff_period(now_utc)
                return

            # Backoff finished: reset fallback flag and try transport.rest again
            if self._using_fallback:
                self._using_fallback = False
                _LOGGER.info(
                    "[backoff] Backoff expired for stop %s, switching back to transport.rest",
                    self.stop_id,
                )

            # Attempt to fetch departures from primary API
            departures = await self.fetch_departures()
            if departures is None:
                await self._handle_failed_fetch(now_utc)
            else:
                self._handle_successful_fetch(departures, now_utc)

    async def _handle_backoff_period(self, now_utc: datetime) -> None:
        """Handle requests during backoff period.
        
        When in backoff, the sensor uses cached data if available. The entity
        is kept available to preserve attributes (health_status, last_updated, etc)
        which are important for debugging API issues.
        """
        # Keep entity available so attributes remain visible during backoff
        self._attr_available = True

        if not BVG_FALLBACK_ENABLED:
            _LOGGER.debug(
                "Skipping API request for stop %s due to backoff until %s",
                self.stop_id,
                self._next_retry_at,
            )
            return

        _LOGGER.debug(
            "[backoff] Stop %s in backoff until %s, attempting BVG fallback API",
            self.stop_id,
            self._next_retry_at,
        )

        # Try BVG fallback during backoff
        departures = await self._fetch_bvg_fallback()
        if departures is not None:
            self._consecutive_failures = 0
            self.last_update_success = now_utc
            self._data_source = "bvg_api"
            self._attr_available = True
            self.departures = departures
            self._invalidate_attributes_cache()
            _LOGGER.info(
                "[fallback] BVG API provided departures during backoff for stop %s",
                self.stop_id,
            )

    async def _handle_failed_fetch(self, now_utc: datetime) -> None:
        """Handle failed API fetch with exponential backoff and fallback activation.
        
        Implements exponential backoff strategy:
        - 1st failure: 120s (2 min)
        - 2nd failure: 240s (4 min)  
        - 3rd failure: 480s (8 min)
        - ...up to max 900s (15 min)
        
        Attempts BVG fallback API immediately on failure if enabled.
        Sets entity to unavailable only if no cached data exists (otherwise remains
        available with stale data). Activates fallback mode to allow BVG API retries.
        
        Args:
            now_utc: Current UTC time for calculating next retry window
        """
        self._consecutive_failures += 1
        backoff_seconds = min(
            BACKOFF_MAX_SECONDS,
            SCAN_INTERVAL.total_seconds() * (BACKOFF_BASE ** (self._consecutive_failures - 1)),
        )
        self._next_retry_at = now_utc + timedelta(seconds=backoff_seconds)
        self._using_fallback = True
        # Keep entity available so attributes (health_status, last_updated, etc) remain visible
        # The state value ("N/A" vs departure time) indicates whether data is available
        self._attr_available = True

        # Try BVG fallback IMMEDIATELY on failure (don't wait for next poll cycle)
        if BVG_FALLBACK_ENABLED:
            departures = await self._fetch_bvg_fallback()
            if departures is not None:
                self.departures = departures
                self._data_source = "bvg_api"
                self.last_update_success = now_utc
                self._consecutive_failures = 0
                self._next_retry_at = None
                self._using_fallback = False
                _LOGGER.info(
                    "[fallback] BVG API recovered departures immediately after transport.rest failure "
                    "for stop %s",
                    self.stop_id,
                )
                return

        # BVG fallback failed or disabled: use cached data if available
        if not self.departures:
            _LOGGER.warning(
                "[backoff] No cached departures for stop %s after API failure "
                "(%s consecutive failures)",
                self.stop_id,
                self._consecutive_failures,
            )
            return

        if self._is_within_fallback(now_utc):
            _LOGGER.warning(
                "[backoff] Using cached departures for stop %s after API failure "
                "(%s consecutive failures)",
                self.stop_id,
                self._consecutive_failures,
            )
        else:
            _LOGGER.warning(
                "[backoff] Using stale cached departures for stop %s after API failure "
                "(%s consecutive failures)",
                self.stop_id,
                self._consecutive_failures,
            )

    def _handle_successful_fetch(
        self, departures: list[Departure], now_utc: datetime
    ) -> None:
        """Handle successful API fetch."""
        self._consecutive_failures = 0
        self._next_retry_at = None
        self._using_fallback = False
        self.last_update_success = now_utc
        self._data_source = "transport.rest"
        self._attr_available = True
        self.departures = departures
        self._invalidate_attributes_cache()

    def _log_departure_fetch_error(self, ex: Exception) -> None:
        if isinstance(ex, aiohttp.ClientResponseError):
            if ex.status == 429:
                retry_after = ex.headers.get("Retry-After") if ex.headers else None
                _LOGGER.warning(
                    "[transport.rest] Rate limited (stop_id=%s, status=%s, retry_after=%s)",
                    self.stop_id,
                    ex.status,
                    retry_after,
                )
                return
            _LOGGER.warning(
                "[transport.rest] HTTP error (stop_id=%s, status=%s)",
                self.stop_id,
                ex.status,
            )
            return

        if isinstance(ex, aiohttp.ClientConnectorError):
            _LOGGER.warning("[transport.rest] Connection error (stop_id=%s): %s", self.stop_id, ex)
            return

        if isinstance(ex, aiohttp.ServerDisconnectedError):
            _LOGGER.warning(
                "[transport.rest] Server disconnected (stop_id=%s): %s", self.stop_id, ex
            )
            return

        if isinstance(ex, aiohttp.ClientError):
            _LOGGER.warning("[transport.rest] Client error (stop_id=%s): %s", self.stop_id, ex)
            return

        if isinstance(ex, TimeoutError):
            _LOGGER.warning("[transport.rest] Request timeout (stop_id=%s): %s", self.stop_id, ex)
            return

        _LOGGER.exception("[transport.rest] Unexpected error (stop_id=%s): %s", self.stop_id, ex)

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
                "[fallback] Cannot use fallback API for stop %s (no sensor_name)",
                self.stop_id,
            )
            return None

        _LOGGER.debug(
            "[fallback] Attempting BVG fallback API for stop '%s' (stop_id=%s)",
            self.sensor_name,
            self.stop_id,
        )

        # Build transport type filters to match transport.rest behavior
        transport_type_filters = {
            "suburban": self.config.get(CONF_TYPE_SUBURBAN, True),
            "subway": self.config.get(CONF_TYPE_SUBWAY, True),
            "tram": self.config.get(CONF_TYPE_TRAM, True),
            "bus": self.config.get(CONF_TYPE_BUS, True),
            "ferry": self.config.get(CONF_TYPE_FERRY, True),
            "express": self.config.get(CONF_TYPE_EXPRESS, True),
            "regional": self.config.get(CONF_TYPE_REGIONAL, True),
        }

        # Choose direction filter: use direction_name if available,
        # otherwise fall back to direction ID (which won't work well with BVG filtering)
        direction_filter = None
        if self.direction_name:
            direction_filter = self.direction_name
            _LOGGER.debug(
                "[fallback] Using direction_name for BVG filtering (direction_name='%s')",
                self.direction_name,
            )

        # Fetch, parse, and filter departures in one call
        parsed_departures = await fetch_and_parse_bvg_departures(
            session=self.session,
            stop_name=self.sensor_name,
            max_journeys=API_MAX_RESULTS,
            timeout_seconds=API_REQUEST_TIMEOUT,
            direction_filter=direction_filter,
            transport_type_filters=transport_type_filters,
        )

        if not parsed_departures:
            _LOGGER.warning(
                "[fallback] BVG API returned no departures for stop '%s' (stop_id=%s). "
                "This may indicate the stop is not covered by BVG API (only covers Berlin).",
                self.sensor_name,
                self.stop_id,
            )
            return None

        self._data_source = "bvg_api"  # Mark that we're using fallback source
        _LOGGER.info(
            "[fallback] BVG API successfully provided %s departures for stop '%s' (stop_id=%s) "
            "(note: limited data - no warnings or vehicle cancellations)",
            len(parsed_departures),
            self.sensor_name,
            self.stop_id,
        )

        return parsed_departures

    def _backfill_direction_name_from_departures(
        self, departures: list[Departure]
    ) -> None:
        """Extract and store direction name from API response for future BVG fallback.
        
        v0.1.4.2+: When a SINGLE direction filter is configured and direction_name
        not yet stored, extract it from first departure's direction field (contains
        clear text name from transport.rest API). This collects direction names to
        support BVG fallback filtering in future versions (v0.1.5+).
        
        Only executes if EXTRACT_AND_STORE_DIRECTION_NAME is enabled AND user has
        configured a SINGLE direction filter (no commas). Multi-direction filters
        are not supported for direction_name extraction due to BVG API limitations.
        
        Args:
            departures: List of Departure objects from transport.rest response
        """
        if not EXTRACT_AND_STORE_DIRECTION_NAME:
            return
        
        # Only extract if user has configured a SINGLE direction filter
        # (skip if no direction or if multiple directions are configured)
        if not self.direction or "," in self.direction:
            return
        
        # Only backfill if not already set
        if self.direction_name:
            return
        
        # Extract from first departure if available
        if departures and departures[0].direction:
            self.direction_name = departures[0].direction
            _LOGGER.debug(
                "[backfill] Extracted direction_name '%s' for stop %s (direction=%s)",
                self.direction_name,
                self.stop_id,
                self.direction,
            )
            # Note: Config persistence requires async_update_entry (implement in v0.1.5)

    def _build_transport_params(self, direction: str | None) -> dict[str, Any]:
        """Build API request parameters for transport.rest API.
        
        Constructs query parameters including departure time (adjusted for walking time),
        result limits, duration window, and transport type filters (configured by user).
        
        Args:
            direction: Optional direction filter string (empty string if None)
        
        Returns:
            Dictionary of API parameters ready to send to transport.rest endpoint
        """
        return {
            "when": (
                self._get_now_utc() + timedelta(minutes=self.walking_time)
            ).isoformat(),
            "results": API_MAX_RESULTS,
            "duration": self.duration,
            "direction": direction or "",
            "suburban": str(bool(self.config.get(CONF_TYPE_SUBURBAN))).lower(),
            "subway": str(bool(self.config.get(CONF_TYPE_SUBWAY))).lower(),
            "tram": str(bool(self.config.get(CONF_TYPE_TRAM))).lower(),
            "bus": str(bool(self.config.get(CONF_TYPE_BUS))).lower(),
            "ferry": str(bool(self.config.get(CONF_TYPE_FERRY))).lower(),
            "express": str(bool(self.config.get(CONF_TYPE_EXPRESS))).lower(),
            "regional": str(bool(self.config.get(CONF_TYPE_REGIONAL))).lower(),
        }

    def _get_excluded_stops(self) -> list[str]:
        """Parse comma-separated excluded stop IDs from configuration.
        
        Returns:
            List of stop IDs (as strings) to exclude from results. Empty list if
            no stops are configured for exclusion.
        """
        if self.excluded_stops is None:
            return []
        return [
            stop.strip()
            for stop in self.excluded_stops.split(",")
            if stop.strip()
        ]

    def _parse_departures(
        self, departures_data: list[dict], excluded_stops: list[str]
    ) -> list[Departure]:
        """Parse departures from API response, filtering by excluded stops.
        
        Converts raw JSON departure objects to Departure dataclass instances.
        Silently skips malformed entries (missing required fields) and stops
        in the excluded stops list.
        
        Args:
            departures_data: Raw departure dictionaries from API response
            excluded_stops: List of stop IDs to exclude from results
        
        Returns:
            List of successfully parsed Departure objects, may be empty if all
            entries are malformed or excluded.
        """
        parsed = []
        for departure in departures_data:
            if departure.get("stop", {}).get("id") in excluded_stops:
                continue
            try:
                parsed.append(Departure.from_dict(departure))
            except (KeyError, TypeError, ValueError) as ex:
                _LOGGER.debug(
                    "[parser] Skipping malformed departure for stop %s: %s",
                    self.stop_id,
                    ex,
                )
        return parsed

    def _update_cache(
        self, request_key: str, response_etag: str | None, parsed: list[Departure]
    ) -> None:
        """Update ETag and departure cache with TTL-based cleanup.
        
        Stores the API response with its ETag for future cache validation. Old cache
        entries (older than CACHE_TTL_SECONDS) are automatically removed to prevent
        unbounded memory growth when users change direction filters or other config.
        
        Args:
            request_key: Unique key combining stop_id and direction parameters
            response_etag: ETag header from API response (None if not provided)
            parsed: Parsed list of Departure objects from API response
        """
        if response_etag:
            self._etag_by_request[request_key] = response_etag
            self._cached_departures_by_request[request_key] = copy.deepcopy(parsed)

            # Track or refresh timestamp for this request key
            now_utc = self._get_now_utc()
            self._cache_request_keys[request_key] = now_utc

            # Remove entries older than CACHE_TTL_SECONDS
            # (user changed config or direction is outdated)
            expired_keys = [
                k for k, t in self._cache_request_keys.items()
                if (now_utc - t).total_seconds() > CACHE_TTL_SECONDS
            ]
            for k in expired_keys:
                self._cache_request_keys.pop(k, None)
                self._etag_by_request.pop(k, None)
                self._cached_departures_by_request.pop(k, None)
                _LOGGER.debug(
                    "[cache] Removed stale cache for stop %s (key=%s, age=%dh)",
                    self.stop_id,
                    k,
                    CACHE_TTL_SECONDS // 3600,
                )

    async def fetch_directional_departure(
        self, direction: str | None
    ) -> list[Departure] | None:
        """Fetch departures from transport.rest API for a specific direction.
        
        Makes an HTTP request to the VBB transport.rest API with ETag validation
        to avoid re-fetching unchanged data (304 Not Modified responses). Uses
        cached ETags from previous requests to minimize bandwidth.
        
        Args:
            direction: Direction string to filter results (e.g., "north", "south").
                      None means no direction filtering (return all departures).
        
        Returns:
            List of Departure objects for this direction, or None if the request fails
            or returns 304 Not Modified (cache still valid).
        """
        request_key = self._request_variant_key(direction)
        request_headers = {"User-Agent": API_USER_AGENT}

        known_etag = self._etag_by_request.get(request_key)
        if known_etag:
            request_headers["If-None-Match"] = known_etag

        try:
            params = self._build_transport_params(direction)
            async with async_timeout.timeout(API_REQUEST_TIMEOUT):
                response = await self.session.get(
                    url=f"{API_ENDPOINT}/stops/{self.stop_id}/departures",
                    params=params,
                    headers=request_headers,
                )

                if response.status == 304:
                    cached = self._cached_departures_by_request.get(request_key)
                    if cached:
                        _LOGGER.debug(
                            "[transport.rest] 304 Not Modified "
                            "(stop_id=%s, direction=%s, cached=%d)",
                            self.stop_id,
                            direction or "all",
                            len(cached),
                        )
                        return copy.deepcopy(cached)
                    return None

                response.raise_for_status()
                departures = await response.json()
        except (aiohttp.ClientError, TimeoutError) as ex:
            self._log_departure_fetch_error(ex)
            return None

        departures_data = departures.get("departures") or []
        if not isinstance(departures_data, list):
            _LOGGER.warning(
                "API response for stop %s has unexpected departures format",
                self.stop_id,
            )
            return None

        excluded_stops = self._get_excluded_stops()
        parsed_departures = self._parse_departures(departures_data, excluded_stops)

        self._update_cache(request_key, response.headers.get("ETag"), parsed_departures)
        
        # Log successful fetch
        _LOGGER.debug(
            "[transport.rest] 200 OK (stop_id=%s, direction=%s, departures=%d)",
            self.stop_id,
            direction or "all",
            len(parsed_departures),
        )
        
        return parsed_departures

    async def fetch_departures(self) -> list[Departure] | None:
        """Fetch departures from VBB API with multi-direction support and error resilience.
        
        This method orchestrates the full departure fetching pipeline:
        1. Fetch from primary transport.rest API with direction support
        2. Deduplicate results (when multiple directions include same trip)
        3. Apply Ringbahn direction filters (⟳ and ⟲ symbols)
        4. Remove Berlin suffix from direction names if configured
        5. Filter out excluded stops
        6. Sort by departure time
        
        The method handles:
        - Automatic ETag-based caching to reduce API load
        - Multi-direction queries (comma-separated)
        - Graceful fallback to BVG API when transport.rest fails
        - Proper error recovery without failing on single API errors
        
        Returns:
            Sorted list of Departure objects by timestamp, or None if all
            API requests fail and no cached data is available.
        """
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

        # Step 1b: Backfill direction_name from API response for BVG filtering (v0.1.5)
        if departures:
            self._backfill_direction_name_from_departures(departures)

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

    def next_departure(self) -> Departure | None:
        """Get the next (earliest) departure from the current list.
        
        Returns:
            The first Departure object from the sorted list (earliest timestamp),
            or None if no departures are available.
        """
        if self.departures and isinstance(self.departures, list):
            return self.departures[0]
        return None
