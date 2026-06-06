"""Sensor entities derived from the GeoSphere nowcast."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfPrecipitationDepth,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import PRECIP_TYPE_OPTIONS, pt_to_text
from .coordinator import (
    GeoSphereData,
    minutes_until_rain,
    precip_next_hour,
    precip_now,
)
from .entity import GeoSphereEntity

if TYPE_CHECKING:
    from . import GeoSphereConfigEntry


@dataclass(frozen=True, kw_only=True)
class GeoSphereSensorEntityDescription(SensorEntityDescription):
    """Sensor description carrying a pure value function."""

    value_fn: Callable[[GeoSphereData], StateType]


def _first(data: GeoSphereData, param: str) -> float | None:
    """First (next-15-min) value of a raw parameter, or None if absent."""
    values = data.params.get(param)
    return values[0] if values else None


SENSORS: tuple[GeoSphereSensorEntityDescription, ...] = (
    GeoSphereSensorEntityDescription(
        key="precipitation",
        translation_key="precipitation",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=precip_now,
    ),
    GeoSphereSensorEntityDescription(
        key="precip_next_hour",
        translation_key="precip_next_hour",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=precip_next_hour,
    ),
    GeoSphereSensorEntityDescription(
        key="minutes_until_rain",
        translation_key="minutes_until_rain",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=minutes_until_rain,
    ),
    GeoSphereSensorEntityDescription(
        key="precipitation_type",
        translation_key="precipitation_type",
        device_class=SensorDeviceClass.ENUM,
        options=PRECIP_TYPE_OPTIONS,
        value_fn=lambda data: (
            pt_to_text(data.params["pt"][0]) if data.params.get("pt") else None
        ),
    ),
    GeoSphereSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            data.params["t2m"][0] if data.params.get("t2m") else None
        ),
    ),
    GeoSphereSensorEntityDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            data.params["rh2m"][0] if data.params.get("rh2m") else None
        ),
    ),
    GeoSphereSensorEntityDescription(
        key="dew_point",
        translation_key="dew_point",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _first(data, "td"),
    ),
    GeoSphereSensorEntityDescription(
        key="wind_speed",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _first(data, "ff"),
    ),
    GeoSphereSensorEntityDescription(
        key="wind_gust",
        translation_key="wind_gust",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _first(data, "fx"),
    ),
    GeoSphereSensorEntityDescription(
        key="wind_direction",
        translation_key="wind_direction",
        native_unit_of_measurement=DEGREE,
        icon="mdi:compass-outline",
        value_fn=lambda data: _first(data, "dd"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoSphereConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        GeoSphereSensor(coordinator, entry, description) for description in SENSORS
    )


class GeoSphereSensor(GeoSphereEntity, SensorEntity):
    """A single derived nowcast sensor."""

    entity_description: GeoSphereSensorEntityDescription

    def __init__(
        self, coordinator, entry, description: GeoSphereSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> StateType:
        data = self.coordinator.data
        if data is None:
            return None
        try:
            return self.entity_description.value_fn(data)
        except (IndexError, KeyError, TypeError):
            return None
