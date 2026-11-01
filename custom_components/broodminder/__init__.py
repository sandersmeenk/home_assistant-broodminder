"""BroodMinder component."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.bluetooth import BluetoothScanningMode, BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

from .ble_parser import ManufacturerData, parse_manufacturer_data
from .brood_tracker import BroodTracker, async_remove_brood_history
from .const import BROOD_MODELS, CONF_MODEL, DOMAIN, MANUFACTURER_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class BroodMinderData:
    """What a config entry keeps while it is loaded."""

    coordinator: PassiveBluetoothProcessorCoordinator
    brood_tracker: BroodTracker | None  # only for models measuring in-hive temperature


def _update_method(service_info: BluetoothServiceInfoBleak) -> ManufacturerData | None:
    """Parse incoming advertisements into our high-level ManufacturerData."""
    if MANUFACTURER_ID not in service_info.manufacturer_data:
        return None

    return parse_manufacturer_data(service_info.address, service_info.manufacturer_data)


@callback
def _async_store_model(hass: HomeAssistant, entry: ConfigEntry, model: int) -> None:
    """Store the model of an entry created before 0.5.0; a hive reloads to get brood."""
    if CONF_MODEL in entry.data:
        return

    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MODEL: model})
    if model in BROOD_MODELS:
        hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BroodMinder BLE from a config entry."""
    address = entry.unique_id  # Bluetooth device address
    brood_tracker: BroodTracker | None = None

    def _update_and_track(service_info: BluetoothServiceInfoBleak) -> ManufacturerData | None:
        parsed = _update_method(service_info)
        if parsed is not None:
            _async_store_model(hass, entry, parsed.model)
            if brood_tracker is not None:
                brood_tracker.async_set_hive_temperature(parsed.temperature_c)
        return parsed

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.ACTIVE,
        update_method=_update_and_track,
    )

    if entry.data.get(CONF_MODEL) in BROOD_MODELS:
        brood_tracker = BroodTracker(hass, entry, lambda: coordinator.available)
        await brood_tracker.async_start()
        entry.async_on_unload(brood_tracker.async_stop)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = BroodMinderData(coordinator, brood_tracker)
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the stored brood history of a removed BroodMinder."""
    await async_remove_brood_history(hass, entry)
