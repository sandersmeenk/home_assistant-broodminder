"""BroodMinder component."""

from __future__ import annotations

import logging

from homeassistant.components.bluetooth import BluetoothScanningMode, BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .ble_parser import ManufacturerData, parse_manufacturer_data
from .const import DOMAIN, MANUFACTURER_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _update_method(service_info: BluetoothServiceInfoBleak) -> ManufacturerData | None:
    """Parse incoming advertisements into our high-level ManufacturerData."""
    if MANUFACTURER_ID not in service_info.manufacturer_data:
        return None

    return parse_manufacturer_data(service_info.address, service_info.manufacturer_data)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BroodMinder BLE from a config entry."""
    address = entry.unique_id  # Bluetooth device address

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.ACTIVE,
        update_method=_update_method,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start after platforms subscribe
    entry.async_on_unload(coordinator.async_start())

    _LOGGER.info("Initialized BroodMinder %s", address)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a BroodMinder config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
