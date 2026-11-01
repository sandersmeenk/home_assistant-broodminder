"""Platform for sensor integration."""

from __future__ import annotations

from datetime import datetime
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
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .ble_parser import ManufacturerData, extract_entities
from .const import (
    ATTR_DESCRIPTION,
    DOMAIN,
    MANUFACTURER,
    SENSOR_BATT,
    SENSOR_HUM,
    SENSOR_SAMPLE_COUNT,
    SENSOR_SWARM_STATE,
    SENSOR_SWARM_TIME,
    SENSOR_TEMP,
    SENSOR_TEMP_RT,
    SENSOR_WEIGHT_L,
    SENSOR_WEIGHT_L2,
    SENSOR_WEIGHT_R,
    SENSOR_WEIGHT_R2,
    SENSOR_WEIGHT_REALTIME,
    SWARM_STATE_DESCRIPTION_UNKNOWN,
    SWARM_STATE_DESCRIPTIONS,
)

_LOGGER = logging.getLogger(__name__)


class BMDescriptions:
    """Entity descriptions for all BroodMinder sensors."""

    temperature: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_TEMP, icon="mdi:thermometer", suggested_display_precision=1
    )
    temperature_rt: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_TEMP_RT, icon="mdi:thermometer", suggested_display_precision=1
    )
    humidity: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_HUM,
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.HUMIDITY,
    )
    battery: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_BATT, icon="mdi:battery", device_class=SensorDeviceClass.BATTERY
    )
    sample_count: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_SAMPLE_COUNT, icon="mdi:counter"
    )
    weight_l: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_L,
        icon="mdi:scale",
        device_class=SensorDeviceClass.WEIGHT,
        suggested_display_precision=2,
    )
    weight_r: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_R,
        icon="mdi:scale",
        device_class=SensorDeviceClass.WEIGHT,
        suggested_display_precision=2,
    )
    weight_l2: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_L2,
        icon="mdi:scale",
        device_class=SensorDeviceClass.WEIGHT,
        suggested_display_precision=2,
    )
    weight_r2: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_R2,
        icon="mdi:scale",
        device_class=SensorDeviceClass.WEIGHT,
        suggested_display_precision=2,
    )
    weight_rt: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_WEIGHT_REALTIME,
        icon="mdi:scale",
        device_class=SensorDeviceClass.WEIGHT,
        suggested_display_precision=2,
    )
    swarm_state: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_SWARM_STATE, icon="mdi:bee"
    )
    swarm_time: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_SWARM_TIME, icon="mdi:clock-outline"
    )


DESCRIPTIONS = BMDescriptions()


def swarm_state_description(swarm_state: int) -> str:
    """Return the human readable description of a SwarmMinder state code."""
    return SWARM_STATE_DESCRIPTIONS.get(swarm_state, SWARM_STATE_DESCRIPTION_UNKNOWN)


def sensor_update_to_bluetooth_data_update(
    parsed: ManufacturerData | None,
) -> PassiveBluetoothDataUpdate[Any]:
    """Build a PassiveBluetoothDataUpdate for the processor."""
    if parsed is None:
        # Advertisement without readable BroodMinder data: keep the last values
        return PassiveBluetoothDataUpdate()

    entities = extract_entities(parsed)
    device = DeviceInfo(
        identifiers={(DOMAIN, parsed.device_id)},
        connections={("bluetooth", parsed.address)},
        manufacturer=MANUFACTURER,
        name=parsed.device_name,
        model=parsed.model_name,
        sw_version=parsed.firmware,
    )

    entity_descriptions: dict[PassiveBluetoothEntityKey, SensorEntityDescription] = {}
    entity_data: dict[PassiveBluetoothEntityKey, Any] = {}
    entity_names: dict[PassiveBluetoothEntityKey, str | None] = {}

    def add(key: str, value: Any, description: SensorEntityDescription, name: str) -> None:
        ek = PassiveBluetoothEntityKey(key=key, device_id=parsed.device_id)
        entity_descriptions[ek] = description
        entity_data[ek] = value
        entity_names[ek] = name

    # Temperature
    if SENSOR_TEMP in entities:
        add(SENSOR_TEMP, entities[SENSOR_TEMP], DESCRIPTIONS.temperature, "Temperature")
    if SENSOR_TEMP_RT in entities:
        add(
            SENSOR_TEMP_RT, entities[SENSOR_TEMP_RT], DESCRIPTIONS.temperature_rt, "Realtime Temp"
        )

    # Humidity / Battery / sample count
    if SENSOR_HUM in entities:
        add(SENSOR_HUM, entities[SENSOR_HUM], DESCRIPTIONS.humidity, "Humidity")
    if SENSOR_BATT in entities:
        add(SENSOR_BATT, entities[SENSOR_BATT], DESCRIPTIONS.battery, "Battery")
    if SENSOR_SAMPLE_COUNT in entities:
        add(
            SENSOR_SAMPLE_COUNT,
            entities[SENSOR_SAMPLE_COUNT],
            DESCRIPTIONS.sample_count,
            "Sample count",
        )

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

    # Create entities when new keys appear
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

    # Provide the current value from the processor
    @property
    def native_value(self) -> StateType | datetime:
        """Return the latest value for this sensor."""
        # For timestamp sensors, ensure extract_entities() returns a datetime
        return self.processor.entity_data.get(self.entity_key)

    # Attributes
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return a human readable description of the swarm state."""
        if self.entity_key.key != SENSOR_SWARM_STATE:
            return None
        swarm_state = self.processor.entity_data.get(self.entity_key)
        if swarm_state is None:
            return None
        return {ATTR_DESCRIPTION: swarm_state_description(swarm_state)}

    # Units
    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement for this sensor."""
        key = self.entity_key.key
        if key in (SENSOR_TEMP, SENSOR_TEMP_RT):
            return UnitOfTemperature.CELSIUS
        if key in (SENSOR_HUM, SENSOR_BATT):
            return PERCENTAGE
        if key in (
            SENSOR_WEIGHT_L,
            SENSOR_WEIGHT_R,
            SENSOR_WEIGHT_L2,
            SENSOR_WEIGHT_R2,
            SENSOR_WEIGHT_REALTIME,
        ):
            return UnitOfMass.KILOGRAMS
        # sample count, swarm_time (timestamp) and swarm_state (string) => no unit
        return None

    # Device classes
    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class for this sensor."""
        key = self.entity_key.key
        if key in (SENSOR_TEMP, SENSOR_TEMP_RT):
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
        # sample count,swarm_state: leave without a device class
        return None

    # State class: only for numeric measurements (NOT for timestamp or string)
    @property
    def state_class(self) -> SensorStateClass | None:
        """Return the state class for this sensor."""
        key = self.entity_key.key
        if key in (
            SENSOR_TEMP,
            SENSOR_TEMP_RT,
            SENSOR_HUM,
            SENSOR_BATT,
            SENSOR_WEIGHT_L,
            SENSOR_WEIGHT_R,
            SENSOR_WEIGHT_L2,
            SENSOR_WEIGHT_R2,
            SENSOR_WEIGHT_REALTIME,
        ):
            return SensorStateClass.MEASUREMENT
        # timestamp and swarm_state should not have a state_class
        return None
