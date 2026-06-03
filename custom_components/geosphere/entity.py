"""Shared base entity + device info for GeoSphere entities."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, BASE_URL, DOMAIN
from .coordinator import GeoSphereDataUpdateCoordinator


def geosphere_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build the shared device for one configured point."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="GeoSphere Austria",
        model="INCA nowcast (15min/1km)",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=BASE_URL,
    )


class GeoSphereEntity(CoordinatorEntity[GeoSphereDataUpdateCoordinator]):
    """Base for sensor/binary_sensor entities (weather sets its own device)."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: GeoSphereDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = geosphere_device_info(entry)
