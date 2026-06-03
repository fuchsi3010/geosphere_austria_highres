"""Binary sensor: is rain expected within the next hour?"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import pt_to_text
from .coordinator import minutes_until_rain, rain_expected
from .entity import GeoSphereEntity

if TYPE_CHECKING:
    from . import GeoSphereConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoSphereConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the rain-expected binary sensor."""
    async_add_entities([GeoSphereRainBinarySensor(entry.runtime_data, entry)])


class GeoSphereRainBinarySensor(GeoSphereEntity, BinarySensorEntity):
    """On when rain is forecast within the next hour.

    Its `forecast` attribute + `minutes_until_rain` drive the
    "notify 15 min before rain" automation.
    """

    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_translation_key = "rain_expected"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rain_expected"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return rain_expected(data, self.coordinator.rain_threshold)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if data is None:
            return {}
        rr = data.params.get("rr") or []
        pt = data.params.get("pt") or []
        forecast = [
            {
                "datetime": ts.isoformat() if ts else None,
                "precipitation": rr[i] if i < len(rr) else None,
                "type": pt_to_text(pt[i]) if i < len(pt) else None,
            }
            for i, ts in enumerate(data.timestamps)
        ]
        return {
            "minutes_until_rain": minutes_until_rain(
                data, self.coordinator.rain_threshold
            ),
            "reference_time": (
                data.reference_time.isoformat() if data.reference_time else None
            ),
            "forecast": forecast,
        }
