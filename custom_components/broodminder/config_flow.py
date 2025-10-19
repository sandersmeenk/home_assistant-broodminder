from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, MANUFACTURER_ID


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

        return self.async_create_entry(
            title=f"BroodMinder {discovery_info.address}",
            data={},  # address is unique_id
        )
