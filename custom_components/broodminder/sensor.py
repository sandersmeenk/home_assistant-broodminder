"""Platform for sensor integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .ble_parser import ManufacturerData, extract_entities
from .const import (
    DOMAIN,
    MANUFACTURER,
    SENSOR_BATT,
    SENSOR_ELAPSED_S,
    SENSOR_HUM,
    SENSOR_SWARM_STATE,
    SENSOR_SWARM_TIME,
    SENSOR_TEMP,
    SENSOR_TEMP_RT1,
    SENSOR_TEMP_RT2,
    SENSOR_WEIGHT_L,
    SENSOR_WEIGHT_L2,
    SENSOR_WEIGHT_R,
    SENSOR_WEIGHT_R2,
    SENSOR_WEIGHT_REALTIME,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BMDescriptions:
    temperature: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_TEMP, icon="mdi:thermometer"
    )
    temperature_rt1: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_TEMP_RT1, icon="mdi:thermometer"
    )
    temperature_rt2: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_TEMP_RT2, icon="mdi:thermometer"
    )
    humidity: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_HUM,
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.HUMIDITY,
    )
    battery: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_BATT, icon="mdi:battery", device_class=SensorDeviceClass.BATTERY
    )
    elapsed: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_ELAPSED_S, icon="mdi:timer-outline"
    )
    weight_l: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_L, icon="mdi:scale", device_class=SensorDeviceClass.WEIGHT
    )
    weight_r: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_R, icon="mdi:scale", device_class=SensorDeviceClass.WEIGHT
    )
    weight_l2: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_L2, icon="mdi:scale", device_class=SensorDeviceClass.WEIGHT
    )
    weight_r2: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_R2, icon="mdi:scale", device_class=SensorDeviceClass.WEIGHT
    )
    weight_rt: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_REALTIME, icon="mdi:scale", device_class=SensorDeviceClass.WEIGHT
    )
    swarm_state: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_SWARM_STATE, icon="mdi:bee"
    )
    swarm_time: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_SWARM_TIME, icon="mdi:clock-outline"
    )


DESCRIPTIONS = BMDescriptions()


def sensor_update_to_bluetooth_data_update(
    parsed: ManufacturerData,
) -> PassiveBluetoothDataUpdate[Any]:
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

    entity_descriptions: dict[PassiveBluetoothEntityKey, SensorEntityDescription] = {}
    entity_data: dict[PassiveBluetoothEntityKey, Any] = {}
    entity_names: dict[PassiveBluetoothEntityKey, str | None] = {}

    def add(key: str, value: Any, description: SensorEntityDescription, name: str):
        ek = PassiveBluetoothEntityKey(key=key, device_id=parsed.device_id)
        entity_descriptions[ek] = description
        entity_data[ek] = value
        entity_names[ek] = name

    # Temperature
    if SENSOR_TEMP in entities:
        add(SENSOR_TEMP, entities[SENSOR_TEMP], DESCRIPTIONS.temperature, "Temperature")
    if SENSOR_TEMP_RT1 in entities:
        add(
            SENSOR_TEMP_RT1,
            entities[SENSOR_TEMP_RT1],
            DESCRIPTIONS.temperature_rt1,
            "Realtime Temp 1",
        )
    if SENSOR_TEMP_RT2 in entities:
        add(
            SENSOR_TEMP_RT2,
            entities[SENSOR_TEMP_RT2],
            DESCRIPTIONS.temperature_rt2,
            "Realtime Temp 2",
        )

    # Humidity / Battery / Elapsed
    if SENSOR_HUM in entities:
        add(SENSOR_HUM, entities[SENSOR_HUM], DESCRIPTIONS.humidity, "Humidity")
    if SENSOR_BATT in entities:
        add(SENSOR_BATT, entities[SENSOR_BATT], DESCRIPTIONS.battery, "Battery")
    if SENSOR_ELAPSED_S in entities:
        add(SENSOR_ELAPSED_S, entities[SENSOR_ELAPSED_S], DESCRIPTIONS.elapsed, "Elapsed")

    # Weights
    if SENSOR_WEIGHT_L in entities:
        add(SENSOR_WEIGHT_L, entities[SENSOR_WEIGHT_L], DESCRIPTIONS.weight_l, "Weight Left")
    if SENSOR_WEIGHT_R in entities:
        add(SENSOR_WEIGHT_R, entities[SENSOR_WEIGHT_R], DESCRIPTIONS.weight_r, "Weight Right")
    if SENSOR_WEIGHT_L2 in entities:
        add(SENSOR_WEIGHT_L2, entities[SENSOR_WEIGHT_L2], DESCRIPTIONS.weight_l2, "Weight Left 2")
    if SENSOR_WEIGHT_R2 in entities:
        add(
            SENSOR_WEIGHT_R2, entities[SENSOR_WEIGHT_R2], DESCRIPTIONS.weight_r2, "Weight Right 2"
        )
    if SENSOR_WEIGHT_REALTIME in entities:
        add(
            SENSOR_WEIGHT_REALTIME,
            entities[SENSOR_WEIGHT_REALTIME],
            DESCRIPTIONS.weight_rt,
            "Weight Realtime",
        )

    # Swarm state & Swarm time
    if SENSOR_SWARM_STATE in entities:
        add(
            SENSOR_SWARM_STATE,
            entities[SENSOR_SWARM_STATE],
            DESCRIPTIONS.swarm_state,
            "Swarm State",
        )
    if SENSOR_SWARM_TIME in entities:
        add(SENSOR_SWARM_TIME, entities[SENSOR_SWARM_TIME], DESCRIPTIONS.swarm_time, "Swarm Time")

    return PassiveBluetoothDataUpdate(
        devices={parsed.device_id: device},
        entity_descriptions=entity_descriptions,
        entity_data=entity_data,
        entity_names=entity_names,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the BroodMinder sensors."""
    processor = PassiveBluetoothDataProcessor(sensor_update_to_bluetooth_data_update)

    # Entities subscribe first
    entry.async_on_unload(
        processor.async_add_entities_listener(BroodMinderSensorEntity, async_add_entities)
    )

    # Get coordinator stored by __init__.py
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Register the processor with the coordinator
    entry.async_on_unload(coordinator.async_register_processor(processor))


class BroodMinderSensorEntity(
    PassiveBluetoothProcessorEntity[PassiveBluetoothDataProcessor[Any | None, ManufacturerData],],
    SensorEntity,
):
    """Entity for a BroodMinder reading."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        key = self.entity_key.key
        if key in (SENSOR_TEMP, SENSOR_TEMP_RT1, SENSOR_TEMP_RT2):
            return UnitOfTemperature.CELSIUS
        if key == SENSOR_HUM:
            return PERCENTAGE
        if key == SENSOR_BATT:
            return PERCENTAGE
        if key in (
            SENSOR_WEIGHT_L,
            SENSOR_WEIGHT_R,
            SENSOR_WEIGHT_L2,
            SENSOR_WEIGHT_R2,
            SENSOR_WEIGHT_REALTIME,
        ):
            return UnitOfMass.KILOGRAMS
        if key == SENSOR_ELAPSED_S:
            return UnitOfTime.SECONDS
        if key in (SENSOR_SWARM_TIME, SENSOR_SWARM_STATE):
            return None
        return None

    @property
    def device_class(self):
        key = self.entity_key.key
        if key in (SENSOR_TEMP, SENSOR_TEMP_RT1, SENSOR_TEMP_RT2):
            return SensorDeviceClass.TEMPERATURE
        if key == SENSOR_HUM:
            return SensorDeviceClass.HUMIDITY
        if key == SENSOR_BATT:
            return SensorDeviceClass.BATTERY
        if key in (
            SENSOR_WEIGHT_L,
            SENSOR_WEIGHT_R,
            SENSOR_WEIGHT_L2,
            SENSOR_WEIGHT_R2,
            SENSOR_WEIGHT_REALTIME,
        ):
            return SensorDeviceClass.WEIGHT
        if key == SENSOR_SWARM_TIME:
            return SensorDeviceClass.TIMESTAMP
        # elapsed/swarm_state: leave without a device class
        return None
