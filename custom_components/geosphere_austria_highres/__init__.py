"""The GeoSphere Austria High-Res Nowcast integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GeoSphereApiClient
from .const import (
    CONF_RAIN_THRESHOLD,
    DEFAULT_SCAN_INTERVAL,
    RAIN_THRESHOLD_MM,
)
from .coordinator import GeoSphereDataUpdateCoordinator

PLATFORMS = [Platform.WEATHER, Platform.SENSOR, Platform.BINARY_SENSOR]

type GeoSphereConfigEntry = ConfigEntry[GeoSphereDataUpdateCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: GeoSphereConfigEntry
) -> bool:
    """Set up GeoSphere Austria from a config entry."""
    session = async_get_clientsession(hass)
    client = GeoSphereApiClient(session)

    scan_minutes = entry.options.get(CONF_SCAN_INTERVAL)
    update_interval = (
        timedelta(minutes=scan_minutes) if scan_minutes else DEFAULT_SCAN_INTERVAL
    )

    coordinator = GeoSphereDataUpdateCoordinator(
        hass,
        client=client,
        latitude=entry.data[CONF_LATITUDE],
        longitude=entry.data[CONF_LONGITUDE],
        name=entry.title,
        update_interval=update_interval,
        rain_threshold=entry.options.get(CONF_RAIN_THRESHOLD, RAIN_THRESHOLD_MM),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GeoSphereConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant, entry: GeoSphereConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
