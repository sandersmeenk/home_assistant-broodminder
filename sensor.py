from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

from homeassistant import config_entries
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorCoordinator,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.components import bluetooth

from .const import (
    DOMAIN,
    MANUFACTURER_ID,
    MANUFACTURER,
    SENSOR_TEMP,
    SENSOR_HUM,
    SENSOR_BATT,
)
from .ble_parser import parse_manufacturer_data, extract_entities, ParsedAdv

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BMDescriptions:
    temperature: EntityDescription = EntityDescription(
        key=SENSOR_TEMP, icon="mdi:thermometer"
    )
    humidity: EntityDescription = EntityDescription(
        key=SENSOR_HUM,
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.HUMIDITY,
    )
    battery: EntityDescription = EntityDescription(
        key=SENSOR_BATT, icon="mdi:battery", device_class=SensorDeviceClass.BATTERY
    )


DESCRIPTIONS = BMDescriptions()


def _to_update(parsed: ParsedAdv) -> PassiveBluetoothDataUpdate[float | int]:
    """Build a PassiveBluetoothDataUpdate for the processor."""
    entities = extract_entities(parsed)
    device = DeviceInfo(
        identifiers={(DOMAIN, parsed.device_id)},
        connections={("bluetooth", parsed.address)},
        manufacturer=MANUFACTURER,
        name=parsed.device_name,
        model=str(parsed.model),
        sw_version=parsed.firmware,
    )

    entity_descriptions: Mapping[PassiveBluetoothEntityKey, EntityDescription] = {}
    entity_data: Mapping[PassiveBluetoothEntityKey, float | int] = {}
    entity_names: Mapping[PassiveBluetoothEntityKey, str | None] = {}

    def add(key: str, value: float | int, description: EntityDescription, name: str):
        ek = PassiveBluetoothEntityKey(key=key, device_id=parsed.device_id)
        entity_descriptions[ek] = description
        entity_data[ek] = value
        entity_names[ek] = name

    if SENSOR_TEMP in entities:
        add(SENSOR_TEMP, entities[SENSOR_TEMP], DESCRIPTIONS.temperature, "Temperature")
    if SENSOR_HUM in entities:
        add(SENSOR_HUM, entities[SENSOR_HUM], DESCRIPTIONS.humidity, "Humidity")
    if SENSOR_BATT in entities:
        add(SENSOR_BATT, entities[SENSOR_BATT], DESCRIPTIONS.battery, "Battery")

    return PassiveBluetoothDataUpdate(
        devices={parsed.device_id: device},
        entity_descriptions=entity_descriptions,
        entity_data=entity_data,
        entity_names=entity_names,
    )


class BroodMinderProcessor(PassiveBluetoothDataProcessor[float | int]):
    """Convert BLE advertisements to HA sensor updates."""

    def __init__(self) -> None:
        super().__init__(self._update_to_ble)

    @staticmethod
    def _update_to_ble(parsed: ParsedAdv) -> PassiveBluetoothDataUpdate[float | int]:
        return _to_update(parsed)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BroodMinder sensors."""
    coordinator: PassiveBluetoothProcessorCoordinator = hass.data[DOMAIN][
        entry.entry_id
    ]

    processor = BroodMinderProcessor()

    # Create entities once we get the first adv for each device
    entry.async_on_unload(
        processor.async_add_entities_listener(BroodMinderSensor, async_add_entities)
    )

    # Register callback to parse incoming advs
    @bluetooth.callback
    def _discovered(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if MANUFACTURER_ID not in service_info.manufacturer_data:
            return
        parsed = parse_manufacturer_data(
            service_info.address, service_info.manufacturer_data
        )
        if not parsed:
            return
        processor.async_on_update(parsed)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _discovered,
            {"manufacturer_id": MANUFACTURER_ID, "connectable": False},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    entry.async_on_unload(coordinator.async_register_processor(processor))


class BroodMinderSensor(PassiveBluetoothProcessorEntity[float | int], SensorEntity):
    """Entity for a BroodMinder reading."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        if self.entity_key.key == SENSOR_TEMP:
            return UnitOfTemperature.CELSIUS
        if self.entity_key.key == SENSOR_HUM:
            return PERCENTAGE
        if self.entity_key.key == SENSOR_BATT:
            return PERCENTAGE
        return None

    @property
    def device_class(self):
        if self.entity_key.key == SENSOR_TEMP:
            return SensorDeviceClass.TEMPERATURE
        if self.entity_key.key == SENSOR_HUM:
            return SensorDeviceClass.HUMIDITY
        if self.entity_key.key == SENSOR_BATT:
            return SensorDeviceClass.BATTERY
        return None
