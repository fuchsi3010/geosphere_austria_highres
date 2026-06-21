"""Config + options flow for GeoSphere Austria."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LONGITUDE,
    CONF_NAME,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BBOX,
    CONF_DOWNPOUR_THRESHOLD,
    CONF_RAIN_THRESHOLD,
    DOMAIN,
    DOWNPOUR_THRESHOLD_MM,
    RAIN_THRESHOLD_MM,
)


def _in_bbox(latitude: float, longitude: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = BBOX
    return lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max


class GeoSphereConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup: pick a point on the map (defaults to Home)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            location = user_input[CONF_LOCATION]
            latitude = location[CONF_LATITUDE]
            longitude = location[CONF_LONGITUDE]
            if not _in_bbox(latitude, longitude):
                errors["base"] = "outside_austria"
            else:
                await self.async_set_unique_id(
                    f"{round(latitude, 3)}_{round(longitude, 3)}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_LATITUDE: latitude,
                        CONF_LONGITUDE: longitude,
                    },
                )

        suggested_location = {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
        }
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME,
                    default=f"GeoSphere {self.hass.config.location_name}",
                ): str,
                vol.Required(
                    CONF_LOCATION, default=suggested_location
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=False)
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> GeoSphereOptionsFlow:
        return GeoSphereOptionsFlow()


class GeoSphereOptionsFlow(OptionsFlow):
    """Tune the rain threshold and update interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RAIN_THRESHOLD,
                    default=options.get(CONF_RAIN_THRESHOLD, RAIN_THRESHOLD_MM),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=10,
                        step=0.1,
                        unit_of_measurement="mm",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_DOWNPOUR_THRESHOLD,
                    default=options.get(
                        CONF_DOWNPOUR_THRESHOLD, DOWNPOUR_THRESHOLD_MM
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=20,
                        step=0.1,
                        unit_of_measurement="mm",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
