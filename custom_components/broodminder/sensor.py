"""Platform for sensor integration."""

from __future__ import annotations

from collections.abc import Iterable
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import BroodMinderData
from .ble_parser import ManufacturerData, device_name, extract_entities, model_name
from .brood_tracker import BroodTracker
from .const import (
    ATTR_CHARGE_REMAINING,
    ATTR_DESCRIPTION,
    ATTR_HOURS_USED,
    ATTR_LEVEL,
    ATTR_OUTDOOR_ENTITY,
    ATTR_SENSOR_POSITION,
    ATTR_STABILITY,
    ATTR_STATUS,
    ATTR_VOLTAGE_BASED,
    BATTERY_CHARGE_REMAINING,
    BATTERY_VOLTAGE_BASED,
    CONF_MODEL,
    DOMAIN,
    MANUFACTURER,
    SENSOR_BATT,
    SENSOR_BROOD,
    SENSOR_BROOD_BREAK,
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
    brood: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_BROOD,
        icon="mdi:hexagon-multiple",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    )
    brood_break: SensorEntityDescription = SensorEntityDescription(
        key=SENSOR_BROOD_BREAK,
        icon="mdi:hexagon-multiple-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
    )


DESCRIPTIONS = BMDescriptions()

# Keys of the entities the processor creates; restored data may hold keys an older build had
PROCESSOR_ENTITY_KEYS = frozenset(
    {
        SENSOR_TEMP,
        SENSOR_TEMP_RT,
        SENSOR_HUM,
        SENSOR_BATT,
        SENSOR_SAMPLE_COUNT,
        SENSOR_WEIGHT_L,
        SENSOR_WEIGHT_R,
        SENSOR_WEIGHT_L2,
        SENSOR_WEIGHT_R2,
        SENSOR_WEIGHT_REALTIME,
        SENSOR_SWARM_STATE,
        SENSOR_SWARM_TIME,
    }
)


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
    if BATTERY_VOLTAGE_BASED in entities or BATTERY_CHARGE_REMAINING in entities:
        # The Battery entity keeps both kinds of reading; they get no entities of their own
        battery = PassiveBluetoothEntityKey(key=SENSOR_BATT, device_id=parsed.device_id)
        entity_descriptions[battery] = DESCRIPTIONS.battery
        entity_names[battery] = "Battery"
        for key in (BATTERY_VOLTAGE_BASED, BATTERY_CHARGE_REMAINING):
            if key in entities:
                reading = PassiveBluetoothEntityKey(key=key, device_id=parsed.device_id)
                entity_data[reading] = entities[key]
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

    @callback
    def _async_add_processor_entities(entities: Iterable[BroodMinderSensorEntity]) -> None:
        # Leave out keys no longer sent, such as a Charge remaining sensor of an older build
        async_add_entities(
            [entity for entity in entities if entity.entity_key.key in PROCESSOR_ENTITY_KEYS]
        )

    # Create entities when new keys appear
    entry.async_on_unload(
        processor.async_add_entities_listener(_create_entity, _async_add_processor_entities)
    )

    # Get coordinator and brood tracker stored by __init__.py
    data: BroodMinderData = hass.data[DOMAIN][entry.entry_id]

    # Register the processor with the coordinator; with the description class, Home Assistant
    # restores the last values after a restart, so sensors don't wait for the next advertisement
    entry.async_on_unload(
        data.coordinator.async_register_processor(processor, SensorEntityDescription)
    )

    if data.brood_tracker is not None:
        address, model = data.coordinator.address, entry.data[CONF_MODEL]
        async_add_entities(
            [
                BroodMinderBroodSensor(data.brood_tracker, address, model),
                BroodMinderBroodBreakSensor(data.brood_tracker, address, model),
            ]
        )


class BroodTrackerSensor(SensorEntity):
    """Sensor on a hive's device whose value comes from the hive's brood tracker."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, tracker: BroodTracker, address: str, model: int) -> None:
        """Initialize the sensor on the hive's device, also before it has advertised."""
        self._tracker = tracker
        self._attr_unique_id = f"{address}-{self.entity_description.key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer=MANUFACTURER,
            name=device_name(address, model),
            model=model_name(model),
        )


class BroodMinderBroodSensor(BroodTrackerSensor):
    """Brood estimate of a hive, from its temperature and the outdoor temperature."""

    _attr_name = "Brood"
    entity_description = DESCRIPTIONS.brood

    async def async_added_to_hass(self) -> None:
        """Update the state after every sample."""
        self.async_on_remove(self._tracker.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> int | None:
        """Return the brood estimate in percent."""
        return self._tracker.estimate.brood_percent

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return how the estimate was made, and why it may be unknown."""
        estimate = self._tracker.estimate
        return {
            ATTR_STATUS: self._tracker.status,
            ATTR_LEVEL: None if estimate.level is None else round(estimate.level, 2),
            ATTR_STABILITY: None if estimate.stability is None else round(estimate.stability, 2),
            ATTR_HOURS_USED: estimate.hours_used,
            ATTR_OUTDOOR_ENTITY: self._tracker.outdoor_entity_id,
            ATTR_SENSOR_POSITION: self._tracker.position,
        }


class BroodMinderBroodBreakSensor(BroodTrackerSensor):
    """When a hive's likely brood break started, or unknown without one."""

    _attr_name = "Likely brood break since"
    entity_description = DESCRIPTIONS.brood_break

    def __init__(self, tracker: BroodTracker, address: str, model: int) -> None:
        """Initialize the sensor with the brood break the tracker loaded."""
        super().__init__(tracker, address, model)
        self._attr_native_value = self._since()

    async def async_added_to_hass(self) -> None:
        """Follow the tracker's samples."""
        self.async_on_remove(self._tracker.async_add_listener(self._async_sampled))

    @callback
    def _async_sampled(self) -> None:
        """Write the state only when a break starts or ends, so the recorder stays idle."""
        since = self._since()
        if since != self._attr_native_value:
            self._attr_native_value = since
            self.async_write_ha_state()

    def _since(self) -> datetime | None:
        since = self._tracker.brood_break.since
        return None if since is None else dt_util.utc_from_timestamp(since)


def _create_entity(
    processor: PassiveBluetoothDataProcessor[Any | None, ManufacturerData],
    entity_key: PassiveBluetoothEntityKey,
    description: SensorEntityDescription,
) -> BroodMinderSensorEntity:
    """Create the entity for a key; Battery combines two kinds of reading."""
    if entity_key.key == SENSOR_BATT:
        return BroodMinderBatterySensor(processor, entity_key, description)
    return BroodMinderSensorEntity(processor, entity_key, description)


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
        value = self.processor.entity_data.get(self.entity_key)
        if self.entity_key.key == SENSOR_SWARM_TIME and isinstance(value, str):
            # Restored after a restart: the saved values hold the time as text
            return dt_util.parse_datetime(value)
        return value

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


class BroodMinderBatterySensor(BroodMinderSensorEntity):
    """Battery: the lower of the last voltage based and charge remaining readings.

    Newer firmware sends charge remaining in place of the voltage based reading, roughly every
    other reading. The processor keeps the last of each, and restores them after a restart.
    """

    async def async_added_to_hass(self) -> None:
        """Follow both kinds of reading, which have no entities of their own."""
        await super().async_added_to_hass()
        for key in (BATTERY_VOLTAGE_BASED, BATTERY_CHARGE_REMAINING):
            self.async_on_remove(
                self.processor.async_add_entity_key_listener(
                    self._handle_processor_update,
                    PassiveBluetoothEntityKey(key, self.entity_key.device_id),
                )
            )

    def _reading(self, key: str) -> int | None:
        return self.processor.entity_data.get(
            PassiveBluetoothEntityKey(key, self.entity_key.device_id)
        )

    @property
    def native_value(self) -> int | None:
        """Return the lower of the readings."""
        readings = [
            reading
            for reading in (
                self._reading(BATTERY_VOLTAGE_BASED),
                self._reading(BATTERY_CHARGE_REMAINING),
            )
            if reading is not None
        ]
        return min(readings, default=None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the readings behind the battery level."""
        return {
            ATTR_VOLTAGE_BASED: self._reading(BATTERY_VOLTAGE_BASED),
            ATTR_CHARGE_REMAINING: self._reading(BATTERY_CHARGE_REMAINING),
        }
