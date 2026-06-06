"""Weather entity backed by the GeoSphere nowcast."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.weather import (
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, STEPS_PER_HOUR, derive_condition
from .coordinator import GeoSphereDataUpdateCoordinator, hourly_forecast
from .entity import geosphere_device_info

if TYPE_CHECKING:
    from . import GeoSphereConfigEntry


def _first(arr: list | None):
    return arr[0] if arr else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoSphereConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the weather entity."""
    async_add_entities([GeoSphereWeather(entry.runtime_data, entry)])


class GeoSphereWeather(
    SingleCoordinatorWeatherEntity[GeoSphereDataUpdateCoordinator]
):
    """Current conditions + hourly forecast from the nowcast."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = geosphere_device_info(entry)

    @property
    def condition(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        rr0 = _first(data.params.get("rr"))
        # rr0 is mm in the next 15 min; condition wants a rate (mm/h).
        rate = rr0 * STEPS_PER_HOUR if rr0 is not None else None
        return derive_condition(rate, _first(data.params.get("pt")))

    @property
    def native_temperature(self) -> float | None:
        return _first(self.coordinator.data.params.get("t2m"))

    @property
    def native_dew_point(self) -> float | None:
        return _first(self.coordinator.data.params.get("td"))

    @property
    def humidity(self) -> float | None:
        return _first(self.coordinator.data.params.get("rh2m"))

    @property
    def native_wind_speed(self) -> float | None:
        return _first(self.coordinator.data.params.get("ff"))

    @property
    def native_wind_gust_speed(self) -> float | None:
        return _first(self.coordinator.data.params.get("fx"))

    @property
    def wind_bearing(self) -> float | None:
        return _first(self.coordinator.data.params.get("dd"))

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        data = self.coordinator.data
        if data is None:
            return None
        current_hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        forecasts: list[Forecast] = []
        for item in hourly_forecast(data):
            if item["datetime"] < current_hour:
                continue
            forecasts.append(
                Forecast(
                    datetime=item["datetime"].isoformat(),
                    condition=item["condition"],
                    native_temperature=item["temperature"],
                    native_precipitation=item["precipitation"],
                    humidity=item["humidity"],
                    native_wind_speed=item["wind_speed"],
                    wind_bearing=item["wind_bearing"],
                )
            )
        return forecasts
