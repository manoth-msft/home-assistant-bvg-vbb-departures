"""The Berlin (BVG) and Brandenburg (VBB) transport integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    PRIM_API_ENDPOINT,
    SEC_API_ENDPOINT,
    CONF_DEPARTURES_STOP_ID,
    CONF_DEPARTURES_DIRECTION,
    CONF_TYPE_SUBURBAN,
    CONF_TYPE_SUBWAY,
    CONF_TYPE_TRAM,
    CONF_TYPE_BUS,
    CONF_TYPE_FERRY,
    CONF_TYPE_EXPRESS,
    CONF_TYPE_REGIONAL,
    DIRECTION_MIGRATION_STATE,
    DIRECTION_ID_MIGRATION_ENABLED,
)
from .config_flow import get_direction_stops

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def _migrate_direction_field(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate direction field from Stop-Name text to numeric Stop-ID.

    Handles configs created before v0.1.6 where users might have entered stop names
    instead of stop IDs in the YAML config, causing HTTP 500 errors from the API.

    Args:
        hass: Home Assistant instance
        entry: The config entry to migrate

    Returns:
        True if migration completed (success or intentional skip)
    """
    direction = entry.data.get(CONF_DEPARTURES_DIRECTION)
    migration_state = entry.data.get(DIRECTION_MIGRATION_STATE)

    # Already processed
    if migration_state in ("completed", "failed"):
        return True

    # Not needed: No direction set or already a Stop-ID
    if not direction or (isinstance(direction, str) and direction.isdigit()):
        data = {**entry.data, DIRECTION_MIGRATION_STATE: "not_needed"}
        hass.config_entries.async_update_entry(entry, data=data)
        _LOGGER.debug(
            "[migration] No direction migration needed for stop '%s'",
            entry.data.get("name", "unknown"),
        )
        return True

    # Direction is text → try to convert to Stop-ID
    _LOGGER.info(
        "[migration] Attempting to migrate direction '%s' for stop '%s'",
        direction,
        entry.data.get("name", "unknown"),
    )

    try:
        session = async_get_clientsession(hass)

        # Search for the direction stop
        success, stops, error = await get_direction_stops(session, direction, results=5)

        if not success or not stops:
            # Cannot find stop → mark failed and don't retry
            _LOGGER.error(
                "[migration] Could not convert direction '%s' to Stop-ID (error: %s)",
                direction,
                error,
            )
            data = {**entry.data, DIRECTION_MIGRATION_STATE: "failed"}
            hass.config_entries.async_update_entry(entry, data=data)
            return True

        # Build list of product types from config
        config_products = []
        product_map = {
            CONF_TYPE_SUBURBAN: "suburban",
            CONF_TYPE_SUBWAY: "subway",
            CONF_TYPE_TRAM: "tram",
            CONF_TYPE_BUS: "bus",
            CONF_TYPE_FERRY: "ferry",
            CONF_TYPE_EXPRESS: "express",
            CONF_TYPE_REGIONAL: "regional",
        }

        for conf_type, product_name in product_map.items():
            if entry.data.get(conf_type, False):
                config_products.append(product_name)

        # If no products configured, use all
        if not config_products:
            config_products = list(product_map.values())

        # Find first stop with matching product type
        direction_id = None
        for stop in stops:
            stop_products = stop.get("products", {})
            for product in config_products:
                if stop_products.get(product, False):
                    direction_id = stop["id"]
                    _LOGGER.debug(
                        "[migration] Found direction Stop-ID: %s for text '%s' (product: %s)",
                        direction_id,
                        direction,
                        product,
                    )
                    break
            if direction_id:
                break

        if not direction_id:
            # No stop found with matching products
            _LOGGER.warning(
                "[migration] Could not find direction '%s' with matching products (config has: %s)",
                direction,
                config_products,
            )
            data = {**entry.data, DIRECTION_MIGRATION_STATE: "failed"}
            hass.config_entries.async_update_entry(entry, data=data)
            return True

        # Update entry with Stop-ID
        data = {
            **entry.data,
            CONF_DEPARTURES_DIRECTION: direction_id,
            DIRECTION_MIGRATION_STATE: "completed",
        }
        hass.config_entries.async_update_entry(entry, data=data)
        _LOGGER.info(
            "[migration] Successfully migrated direction '%s' → Stop-ID %s for stop '%s'",
            direction,
            direction_id,
            entry.data.get("name", "unknown"),
        )
        return True

    except Exception as ex:  # pylint: disable=broad-exception-caught
        _LOGGER.error(
            "[migration] Unexpected error migrating direction field: %s", ex
        )
        # Don't mark failed on unexpected errors (might be network issue)
        # Will retry on next startup
        return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""

    # Run direction field migration (non-blocking, happens in background)
    if DIRECTION_ID_MIGRATION_ENABLED:
        try:
            await _migrate_direction_field(hass, entry)
        except Exception as ex:  # pylint: disable=broad-exception-caught
            _LOGGER.error(
                "[setup] Error running direction migration: %s", ex
            )
            # Don't block setup on migration errors

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))
    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


def setup(
    hass: HomeAssistant, config: ConfigType  # pylint: disable=unused-argument
) -> bool:
    return True
