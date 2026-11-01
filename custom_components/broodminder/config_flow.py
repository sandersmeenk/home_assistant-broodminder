"""Config flow for the BroodMinder integration."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN, SensorDeviceClass
from homeassistant.components.weather import DOMAIN as WEATHER_DOMAIN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
    BROOD_MODELS,
    CONF_MODEL,
    CONF_OUTDOOR_ENTITY,
    CONF_SENSOR_POSITION,
    DEFAULT_SENSOR_POSITION,
    DOMAIN,
    IDX_MODEL,
    MANUFACTURER_ID,
    SENSOR_POSITIONS,
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SENSOR_POSITION, default=DEFAULT_SENSOR_POSITION): SelectSelector(
            SelectSelectorConfig(
                options=SENSOR_POSITIONS,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_SENSOR_POSITION,
            )
        ),
        # Empty: Home Assistant's weather is used
        vol.Optional(CONF_OUTDOOR_ENTITY): EntitySelector(
            EntitySelectorConfig(
                filter=[
                    {"domain": SENSOR_DOMAIN, "device_class": SensorDeviceClass.TEMPERATURE},
                    {"domain": WEATHER_DOMAIN},
                ]
            )
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle discovery via Bluetooth."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        if MANUFACTURER_ID not in discovery_info.manufacturer_data:
            return self.async_abort(reason="not_broodminder")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        payload = discovery_info.manufacturer_data[MANUFACTURER_ID]
        return self.async_create_entry(
            title=f"BroodMinder {discovery_info.address}",
            # Address is unique_id; the model decides whether the hive gets a brood estimate
            data={CONF_MODEL: payload[IDX_MODEL]} if payload else {},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: config_entries.ConfigEntry,
    ) -> BroodOptionsFlow:
        """Get the brood settings of a hive."""
        return BroodOptionsFlow()

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: config_entries.ConfigEntry) -> bool:
        """Only models measuring in-hive temperature have brood settings."""
        return config_entry.data.get(CONF_MODEL) in BROOD_MODELS


class BroodOptionsFlow(config_entries.OptionsFlowWithReload):
    """Brood settings of a hive: sensor position and outdoor temperature."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show and save the brood settings."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
