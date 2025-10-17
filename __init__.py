from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BroodMinder BLE from a config entry."""
    address = entry.unique_id  # Bluetooth device address

    # Our parsing is done in sensor via a PassiveBluetoothDataProcessor; coordinator triggers updates.
    coordinator = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = (
        PassiveBluetoothProcessorCoordinator(
            hass,
            _LOGGER,
            address=address,
            mode=BluetoothScanningMode.ACTIVE,  # ensures we also get scan responses when available
            update_method=None,  # We parse in processors; coordinator handles routing
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start after platforms subscribe
    entry.async_on_unload(coordinator.async_start())

    _LOGGER.warning("Initialized BroodMinder %s", address)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a BroodMinder config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
