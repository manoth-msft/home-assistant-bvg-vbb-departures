# mypy: disable-error-code="attr-defined"
# pylint: disable=too-many-lines

"""The Berlin (BVG) and Brandenburg (VBB) transport integration."""

from __future__ import annotations

import asyncio
import logging
import copy
from dataclasses import replace
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
    PRIM_API_ENDPOINT,
    SEC_API_ENDPOINT,
    BVG_API_ENDPOINT,
    API_MAX_RESULTS,
    API_REQUEST_TIMEOUT,
    API_USER_AGENT,
    DEFAULT_DEPARTURES_DURATION,
    DEFAULT_ICON,
    DEFAULT_WALKING_TIME,
    BACKOFF_BASE,
    BACKOFF_MAX_SECONDS,
    PRIM_API_ENABLED,
    SEC_API_ENABLED,
    BVG_FALLBACK_ENABLED,
    CACHE_TTL_SECONDS,
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
    STOP_SUFFIX_BERLIN,
)
from .departure import Departure
from .bvg_api import fetch_and_parse_bvg_departures
from .util import (
    get_direction_stops,
    TRANSPORT_TYPES_SCHEMA,
    validate_excluded_stops,
    validate_walking_time,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DEPARTURES): [
            {
                vol.Required(CONF_DEPARTURES_NAME): cv.string,
                vol.Required(CONF_DEPARTURES_STOP_ID): cv.positive_int,
                vol.Optional(CONF_DEPARTURES_DIRECTION): cv.string,
                vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): validate_excluded_stops,
                vol.Optional(
                    CONF_DEPARTURES_WALKING_TIME, default=1
                ): validate_walking_time,
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
        # Migration: Remove legacy direction_name field from old configs (v0.1.4.x)
        if "direction_name" in config:
            old_direction_name = config.pop("direction_name")
            _LOGGER.debug(
                "[migration] Removed legacy direction_name '%s' from config for stop %s",
                old_direction_name,
                config.get(CONF_DEPARTURES_STOP_ID),
            )
        self.config = config
        self.stop_id: int = config[CONF_DEPARTURES_STOP_ID]
        self.excluded_stops: str | None = config.get(CONF_DEPARTURES_EXCLUDED_STOPS)
        self.sensor_name: str | None = config.get(CONF_DEPARTURES_NAME)
        # Use sensor_name for logging/display, fall back to stop_id if not configured
        self.stop_name: str = self.sensor_name or str(self.stop_id)
        self.direction: str | None = config.get(CONF_DEPARTURES_DIRECTION)
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
            "primary"  # primary, secondary, or bvg_api
        )
        # Track which endpoint (primary/secondary) succeeded
        self._last_successful_endpoint: str | None = None
        # Track if we're in fallback mode (backoff active)
        self._using_fallback: bool = False
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
                await self._handle_backoff_period()
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

    async def _handle_backoff_period(self) -> None:
        """Handle requests during backoff period.

        When in backoff, the sensor uses cached data only. No new API calls are made.
        The entity is kept available to preserve attributes (health_status, last_updated, etc)
        which are important for debugging API issues.
        """
        # Keep entity available so attributes remain visible during backoff
        self._attr_available = True

        _LOGGER.debug(
            "[backoff] Stop %s in backoff until %s, using cached data",
            self.stop_id,
            self._next_retry_at,
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
        else:
            departures = None
        if departures is not None:
            # Smart merge: Only merge if cache is from transport.rest.
            # If cache is from previous BVG fallback, don't merge (BVG + BVG = useless)
            if (
                self.departures
                and self._data_source in ("transport.rest", "transport.rest+bvg_delays")
            ):
                # Cache from transport.rest: merge BVG delays into filtered data
                merged = self._merge_bvg_delays_into_cached_departures(
                    cached_departures=self.departures,
                    bvg_departures=departures,
                )
                self.departures = merged
                self._data_source = "transport.rest+bvg_delays"
            else:
                # No cache or cache is from previous BVG fallback → just use BVG
                self.departures = departures
                self._data_source = "bvg_api"

            self.last_update_success = now_utc
            self._consecutive_failures = 0
            self._next_retry_at = None
            self._using_fallback = False
            _LOGGER.info(
                "[fallback] BVG API updated departures immediately after transport.rest failure "
                "for stop %s (data_source=%s)",
                self.stop_id,
                self._data_source,
            )
            return

        # BVG fallback failed: use cached data if available
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
        # Set data_source based on which endpoint succeeded
        if self._last_successful_endpoint:
            self._data_source = self._last_successful_endpoint
        else:
            self._data_source = "primary"  # Fallback to primary if unknown
        self._attr_available = True
        self.departures = departures
        self._invalidate_attributes_cache()

    def _log_departure_fetch_error(self, ex: Exception) -> None:
        if isinstance(ex, aiohttp.ClientResponseError):
            if ex.status == 429:
                retry_after = ex.headers.get("Retry-After") if ex.headers else None
                _LOGGER.warning(
                    "[transport.rest] Rate limited (stop=%s, status=%s, retry_after=%s)",
                    self.stop_name,
                    ex.status,
                    retry_after,
                )
                return
            _LOGGER.warning(
                "[transport.rest] HTTP error (stop=%s, status=%s)",
                self.stop_name,
                ex.status,
            )
            return

        if isinstance(ex, aiohttp.ClientConnectorError):
            _LOGGER.warning("[transport.rest] Connection error (stop=%s): %s", self.stop_name, ex)
            return

        if isinstance(ex, aiohttp.ServerDisconnectedError):
            _LOGGER.warning(
                "[transport.rest] Server disconnected (stop=%s): %s", self.stop_name, ex
            )
            return

        if isinstance(ex, aiohttp.ClientError):
            _LOGGER.warning("[transport.rest] Client error (stop=%s): %s", self.stop_name, ex)
            return

        if isinstance(ex, TimeoutError):
            _LOGGER.warning("[transport.rest] Request timeout (stop=%s): %s", self.stop_name, ex)
            return

        _LOGGER.exception("[transport.rest] Unexpected error (stop=%s): %s", self.stop_name, ex)

    def _merge_bvg_delays_into_cached_departures(
        self,
        cached_departures: list[Departure],
        bvg_departures: list[Departure],
    ) -> list[Departure]:
        """Merge BVG delay information into cached transport.rest departures.

        Smart fallback strategy: When transport.rest fails, instead of replacing
        well-filtered transport.rest data with unfiltered BVG data, this method
        intelligently merges the two:

        1. Keeps cached transport.rest departures (they have correct direction filtering)
        2. Updates delay information from BVG API (fresh, current data)
        3. Updates warning information from BVG API if available
        4. Adds new departures from BVG that weren't in cache (fills gaps)
        5. Preserves original line type, direction, and other metadata

        This ensures users continue to see correctly-filtered departures while
        getting the most current delay information available.

        Matching strategy: Uses (line_name, time) tuple as key. This is stable across
        both APIs and avoids matching issues with slight timestamp differences.

        Args:
            cached_departures: Original, well-filtered departures from transport.rest
            bvg_departures: Fresh departures from BVG API (may contain unfiltered data)

        Returns:
            List of cached departures with updated delays from BVG, plus new BVG departures
        """
        # Build lookup tables for O(1) matching
        bvg_lookup: dict[tuple[str, str], Departure] = {}
        for dep in bvg_departures:
            key = (dep.line_name, dep.time)
            if key not in bvg_lookup:  # Keep first match (in case of duplicates)
                bvg_lookup[key] = dep

        cache_lookup: dict[tuple[str, str], bool] = {}
        for dep in cached_departures:
            cache_lookup[(dep.line_name, dep.time)] = True

        # Merge: Keep cached departures, update delays from BVG
        merged: list[Departure] = []
        merged_count = 0
        unmatched_count = 0
        new_count = 0

        for cached_dep in cached_departures:
            key = (cached_dep.line_name, cached_dep.time)
            bvg_dep = bvg_lookup.get(key)

            if bvg_dep is not None:
                # Found matching BVG departure: update delay and warnings
                updated_dep = replace(
                    cached_dep,
                    delay=bvg_dep.delay,
                    warnings=bvg_dep.warnings,
                )
                merged.append(updated_dep)
                merged_count += 1
            else:
                # No BVG match: Keep cached departure as-is
                merged.append(cached_dep)
                unmatched_count += 1

        # Add new departures from BVG that weren't in cache
        for bvg_dep in bvg_departures:
            key = (bvg_dep.line_name, bvg_dep.time)
            if key not in cache_lookup:
                merged.append(bvg_dep)
                new_count += 1

        _LOGGER.debug(
            "[merge] Merged BVG delays into cached departures for stop %s: "
            "matched=%d, unmatched=%d (kept old), new=%d (added)",
            self.stop_id,
            merged_count,
            unmatched_count,
            new_count,
        )

        return merged

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

        # Note: BVG API can only filter by endpoint (final destination), but transport.rest
        # filters by intermediate stops. Since we cannot reliably determine if direction_name
        # is an endpoint or just an intermediate stop, we skip direction filtering to avoid
        # incorrectly filtering out valid departures. Only transport type filters are applied.
        _LOGGER.debug(
            "[fallback] Using BVG fallback without direction filtering (only transport types). "
            "BVG API covers Berlin stops and provides full departure list."
        )

        # Fetch, parse, and filter departures in one call
        parsed_departures = await fetch_and_parse_bvg_departures(
            session=self.session,
            stop_name=self.sensor_name,
            max_journeys=API_MAX_RESULTS,
            timeout_seconds=API_REQUEST_TIMEOUT,
            transport_type_filters=transport_type_filters,
        )

        if not parsed_departures:
            _LOGGER.warning(
                "[fallback] BVG API returned no departures after filtering for stop '%s' "
                "(stop_id=%s). This may indicate: (1) the stop is not covered by BVG API "
                "(only covers Berlin), (2) no departures match the configured transport type "
                "filters, or (3) BVG has no data at this time.",
                self.sensor_name,
                self.stop_id,
            )
            return None

        self._data_source = "bvg_api"  # Mark that we're using fallback source
        _LOGGER.info(
            "[fallback] BVG API successfully provided %s departures for stop '%s' (stop_id=%s) "
            "using fallback (note: limited data - no warnings or vehicle cancellations)",
            len(parsed_departures),
            self.sensor_name,
            self.stop_id,
        )

        return parsed_departures

    def _build_transport_params(self, direction: str | None) -> dict[str, Any]:
        """Build API request parameters for transport.rest API.

        Constructs query parameters including departure time (adjusted for walking time),
        result limits, duration window, and transport type filters (configured by user).

        Direction filter is only included if it has a non-empty value, as the API
        rejects empty direction parameters (must be a valid IBNR).

        Args:
            direction: Optional direction filter string (stop IBNR). Only included
                       in params if non-empty.

        Returns:
            Dictionary of API parameters ready to send to transport.rest endpoint
        """
        params = {
            "when": (
                self._get_now_utc() + timedelta(minutes=self.walking_time)
            ).isoformat(),
            "results": API_MAX_RESULTS,
            "duration": self.duration,
            "suburban": str(bool(self.config.get(CONF_TYPE_SUBURBAN))).lower(),
            "subway": str(bool(self.config.get(CONF_TYPE_SUBWAY))).lower(),
            "tram": str(bool(self.config.get(CONF_TYPE_TRAM))).lower(),
            "bus": str(bool(self.config.get(CONF_TYPE_BUS))).lower(),
            "ferry": str(bool(self.config.get(CONF_TYPE_FERRY))).lower(),
            "express": str(bool(self.config.get(CONF_TYPE_EXPRESS))).lower(),
            "regional": str(bool(self.config.get(CONF_TYPE_REGIONAL))).lower(),
        }

        # Only include direction if it has a non-empty value.
        # API rejects empty direction parameters: "direction must be an IBNR"
        if direction:
            params["direction"] = direction

        return params

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

    def _etag_cache_key(self, endpoint_name: str, request_key: str) -> str:
        """Generate endpoint-aware cache key for ETag storage.

        Ensures separate ETags for primary and secondary endpoints, preventing
        ETag collision when APIs return different response data.

        Args:
            endpoint_name: "primary" or "secondary"
            request_key: Base request variant key (stop_id + direction)

        Returns:
            Combined cache key: "endpoint_name:request_key"
        """
        return f"{endpoint_name}:{request_key}"

    def _update_cache(
        self,
        endpoint_name: str,
        request_key: str,
        response_etag: str | None,
        parsed: list[Departure],
    ) -> None:
        """Update ETag and departure cache with TTL-based cleanup.

        Stores the API response with its ETag for future cache validation. Old cache
        entries (older than CACHE_TTL_SECONDS) are automatically removed to prevent
        unbounded memory growth when users change direction filters or other config.

        Args:
            endpoint_name: "primary" or "secondary" endpoint
            request_key: Unique key combining stop_id and direction parameters
            response_etag: ETag header from API response (None if not provided)
            parsed: Parsed list of Departure objects from API response
        """
        cache_key = self._etag_cache_key(endpoint_name, request_key)
        if response_etag:
            self._etag_by_request[cache_key] = response_etag
            self._cached_departures_by_request[cache_key] = copy.deepcopy(parsed)

            # Track or refresh timestamp for this cache key
            now_utc = self._get_now_utc()
            self._cache_request_keys[cache_key] = now_utc

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

    async def _try_fetch_from_endpoint(  # pylint: disable=too-many-locals
        self, endpoint_url: str, endpoint_name: str, direction: str | None
    ) -> list[Departure] | None:
        """Attempt to fetch departures from a specific endpoint with ETag caching.

        Tries a single API endpoint with full ETag validation and error handling.
        Returns None on any failure (HTTP error, timeout, parsing error), allowing
        the caller to fall back to the next endpoint.

        Args:
            endpoint_url: Base URL of the API endpoint (e.g., https://v6.vbb.transport.rest)
            endpoint_name: Name for logging ("primary" or "secondary")
            direction: Direction string to filter results, None for all directions

        Returns:
            List of Departure objects on success, None on any failure.
        """
        request_key = self._request_variant_key(direction)
        cache_key = self._etag_cache_key(endpoint_name, request_key)
        request_headers = {"User-Agent": API_USER_AGENT}

        # Check for cached ETag
        known_etag = self._etag_by_request.get(cache_key)
        if known_etag:
            request_headers["If-None-Match"] = known_etag

        try:
            params = self._build_transport_params(direction)
            async with async_timeout.timeout(API_REQUEST_TIMEOUT):
                response = await self.session.get(
                    url=f"{endpoint_url}/stops/{self.stop_id}/departures",
                    params=params,
                    headers=request_headers,
                )

                if response.status == 304:
                    cached = self._cached_departures_by_request.get(cache_key)
                    if cached:
                        _LOGGER.debug(
                            "[transport.rest] 304 Not Modified "
                            "(endpoint=%s, stop=%s, direction=%s, cached=%d)",
                            endpoint_name,
                            self.stop_name,
                            direction or "all",
                            len(cached),
                        )
                        return copy.deepcopy(cached)
                    return None

                response.raise_for_status()
                departures = await response.json()
        except (aiohttp.ClientError, TimeoutError) as ex:
            _LOGGER.debug(
                "[transport.rest] %s failed for stop %s: %s",
                endpoint_name,
                self.stop_name,
                ex,
            )
            return None

        departures_data = departures.get("departures") or []
        if not isinstance(departures_data, list):
            _LOGGER.warning(
                "API response from %s for stop %s has unexpected departures format",
                endpoint_name,
                self.stop_id,
            )
            return None

        excluded_stops = self._get_excluded_stops()
        parsed_departures = self._parse_departures(departures_data, excluded_stops)

        etag = response.headers.get("ETag")
        self._update_cache(endpoint_name, request_key, etag, parsed_departures)

        # Log successful fetch
        _LOGGER.debug(
            "[transport.rest] 200 OK (endpoint=%s, stop=%s, direction=%s, departures=%d)",
            endpoint_name,
            self.stop_name,
            direction or "all",
            len(parsed_departures),
        )

        return parsed_departures

    async def fetch_directional_departure(
        self, direction: str | None
    ) -> list[Departure] | None:
        """Fetch departures with dual-API failover: primary → secondary → None.

        Implements sequential failover between primary (v6.vbb.transport.rest) and
        secondary (custom instance) endpoints. Only returns None if both fail,
        allowing the caller to invoke backoff and BVG fallback logic.

        Args:
            direction: Direction string to filter results, None for all directions

        Returns:
            List of Departure objects from first successful endpoint, or None if both fail.
        """
        # Try primary endpoint first (if enabled)
        if PRIM_API_ENABLED:
            departures = await self._try_fetch_from_endpoint(
                PRIM_API_ENDPOINT, "primary", direction
            )
            if departures is not None:
                self._last_successful_endpoint = "primary"
                return departures

        # Primary failed or disabled, try secondary endpoint (if enabled)
        if SEC_API_ENABLED:
            _LOGGER.info(
                "[failover] Primary endpoint failed/disabled, "
                "attempting secondary (stop=%s, direction=%s)",
                self.stop_name,
                direction or "all",
            )
            departures = await self._try_fetch_from_endpoint(
                SEC_API_ENDPOINT, "secondary", direction
            )
            if departures is not None:
                self._last_successful_endpoint = "secondary"
                _LOGGER.info(
                    "[failover] Secondary endpoint SUCCESS "
                    "(stop=%s, direction=%s, departures=%d)",
                    self.stop_name,
                    direction or "all",
                    len(departures),
                )
                return departures

        # Both endpoints failed or disabled, trigger backoff + BVG fallback
        _LOGGER.warning(
            "[failover] Primary and secondary endpoints failed/disabled "
            "(stop=%s, direction=%s). Activating backoff + BVG fallback.",
            self.stop_name,
            direction or "all",
        )
        return None

    async def _resolve_direction_to_stopid(  # pylint: disable=too-many-branches
        self, direction: str | None
    ) -> str | None:
        """Convert direction from Stop-Name text to numeric Stop-ID if needed.

        This is a fallback for old configs that have stop names instead of IDs
        in the direction field (v0.1.5 and earlier). It attempts to look up the
        Stop-Name and use the first matching Stop-ID with a product type matching
        the sensor's configuration.

        Args:
            direction: Direction filter (either numeric Stop-ID or Stop-Name text)

        Returns:
            Resolved Stop-ID (string of digits), or original direction if already numeric,
            or None if direction is None or conversion fails.
        """
        if not direction:
            return direction

        # Already a numeric Stop-ID
        if direction.isdigit():
            return direction

        # Text Stop-Name → try to convert
        _LOGGER.debug(
            "[fallback] Direction '%s' is text, attempting to convert to Stop-ID",
            direction,
        )

        try:
            # Search for direction stops
            success, stops, error = await get_direction_stops(
                self.session, direction, results=5
            )

            if not success or not stops:
                _LOGGER.warning(
                    "[fallback] Could not convert direction '%s' (error: %s)",
                    direction,
                    error,
                )
                # Keep original on failure (will likely error from API but worth trying)
                return direction

            # Build list of configured product types
            config_products = []
            if self.config.get(CONF_TYPE_SUBURBAN, False):
                config_products.append("suburban")
            if self.config.get(CONF_TYPE_SUBWAY, False):
                config_products.append("subway")
            if self.config.get(CONF_TYPE_TRAM, False):
                config_products.append("tram")
            if self.config.get(CONF_TYPE_BUS, False):
                config_products.append("bus")
            if self.config.get(CONF_TYPE_FERRY, False):
                config_products.append("ferry")
            if self.config.get(CONF_TYPE_EXPRESS, False):
                config_products.append("express")
            if self.config.get(CONF_TYPE_REGIONAL, False):
                config_products.append("regional")

            # Default to all if none configured
            if not config_products:
                config_products = ["suburban", "subway", "tram", "bus", "ferry", "express", "regional"]

            # Find first stop with matching product
            for stop in stops:
                stop_products = stop.get("products", {})
                for product in config_products:
                    if stop_products.get(product, False):
                        resolved_id = stop["id"]
                        _LOGGER.info(
                            "[fallback] Converted direction '%s' → Stop-ID %s (product: %s)",
                            direction,
                            resolved_id,
                            product,
                        )
                        return resolved_id

            # No stop found with matching products
            _LOGGER.warning(
                "[fallback] Direction '%s' found but no matching products (config has: %s)",
                direction,
                config_products,
            )
            return direction

        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOGGER.error(
                "[fallback] Error converting direction '%s': %s",
                direction,
                ex,
            )
            # On error, keep original and let API error out
            return direction

    async def fetch_departures(self) -> list[Departure] | None:
        """Fetch departures from VBB API with multi-direction support and error resilience.

        This method orchestrates the full departure fetching pipeline:
        1. Resolve direction from text Stop-Name to numeric Stop-ID if needed (v0.1.6+)
        2. Fetch from primary transport.rest API with direction support
        3. Deduplicate results (when multiple directions include same trip)
        4. Apply Ringbahn direction filters (⟳ and ⟲ symbols)
        5. Remove Berlin suffix from direction names if configured
        6. Filter out excluded stops
        7. Sort by departure time

        The method handles:
        - Automatic conversion of Stop-Names to Stop-IDs (fallback for old configs)
        - Automatic ETag-based caching to reduce API load
        - Multi-direction queries (comma-separated)
        - Graceful fallback to BVG API when transport.rest fails
        - Proper error recovery without failing on single API errors

        Returns:
            Sorted list of Departure objects by timestamp, or None if all
            API requests fail and no cached data is available.
        """
        departures = []

        # Step 0: Resolve direction if it's text (fallback for old configs)
        resolved_direction = await self._resolve_direction_to_stopid(self.direction)

        # Step 1: Fetch departures
        if resolved_direction is None:
            res = await self.fetch_directional_departure(resolved_direction)
            if res is None:
                return None
            departures += res
        else:
            for direction in resolved_direction.split(","):
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

    def next_departure(self) -> Departure | None:
        """Get the next (earliest) departure from the current list.

        Returns:
            The first Departure object from the sorted list (earliest timestamp),
            or None if no departures are available.
        """
        if self.departures and isinstance(self.departures, list):
            return self.departures[0]
        return None
