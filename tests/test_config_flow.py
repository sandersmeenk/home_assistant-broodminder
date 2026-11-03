"""End-to-end tests: fake BLE advertisements → discovery → config entries → sensor entities."""

# ruff: noqa: PLR2004

from datetime import UTC, datetime
import time
from typing import Any

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, _get_manager
from homeassistant.config_entries import SOURCE_BLUETOOTH, ConfigEntry, ConfigEntryState
from homeassistant.const import (
    EVENT_HOMEASSISTANT_FINAL_WRITE,
    EVENT_HOMEASSISTANT_STARTED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.broodminder.const import (
    BROOD_SAMPLE_INTERVAL,
    CONF_MODEL,
    CONF_OUTDOOR_ENTITY,
    CONF_SENSOR_POSITION,
    DOMAIN,
    ISSUE_NO_WEATHER_ENTITY,
    ISSUE_OUTDOOR_UNAVAILABLE,
    MANUFACTURER,
    MANUFACTURER_ID,
    POSITION_IN_COMB,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "enable_bluetooth")

TH_ADDRESS = "AA:BB:CC:00:00:01"
SCALE_ADDRESS = "AA:BB:CC:00:00:02"
T_ADDRESS = "AA:BB:CC:00:00:03"
SCALE_W_43_ADDRESS = "AA:BB:CC:00:00:04"
EXTRA_CHANNELS_ADDRESS = "AA:BB:CC:00:00:05"
OTHER_VENDOR_ID = 0x004C

SWARM_TIME = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _le16(payload: bytearray, lo_idx: int, hi_idx: int, value: int) -> None:
    payload[lo_idx] = value & 0xFF
    payload[hi_idx] = (value >> 8) & 0xFF


def _payload(model: int, battery: int, temp_c: float) -> bytearray:
    """Build a full 21-byte payload with the fields every model shares."""
    payload = bytearray(21)
    payload[0] = model
    payload[1] = 2  # v.minor
    payload[2] = 1  # v.major
    payload[4] = battery
    _le16(payload, 5, 6, 1234)  # elapsed / sample count
    raw_temp = round(temp_c * 100) + 5000
    _le16(payload, 7, 8, raw_temp)
    _le16(payload, 3, 9, raw_temp)  # realtime temperature
    return payload


def _th_payload(temp_c: float = 25.0) -> bytes:
    payload = _payload(model=56, battery=90, temp_c=temp_c)
    payload[14] = 55  # humidity
    return bytes(payload)


def _scale_payload() -> bytes:
    payload = _payload(model=57, battery=80, temp_c=15.0)
    _le16(payload, 10, 11, 32767 + 2000)  # left 20.00 kg
    _le16(payload, 12, 13, 32767 + 2150)  # right 21.50 kg
    payload[14] = 60  # humidity
    _le16(payload, 15, 16, 0x7FFF)  # left 2: not connected
    _le16(payload, 17, 18, 0x7FFF)  # right 2: not connected
    _le16(payload, 19, 20, 32767 + 4150)  # realtime total 41.50 kg
    return bytes(payload)


def _scale_w_43_payload() -> bytes:
    """Model 43 advertisement from the BroodMinder docs (87_physics_and_tech_stuff)."""
    return bytes.fromhex(
        "2b"  # model 43
        "1502"  # v.minor, v.major
        "00"  # realtime temperature LSB: not sent by model 43
        "02"  # battery %
        "2100"  # elapsed: 33
        "d062"  # temperature: SHT raw 0x62D0 -> 23.69 °C
        "00"  # realtime temperature MSB: not sent by model 43
        "ff7f"  # weight left: 0.00 kg
        "0580"  # weight right: 0.06 kg
        "37"  # humidity: 55%
        "07304300"  # device id 43:30:07, LSB first: not a weight
        "0000"  # realtime total: not sent by model 43
    )


def _extra_channels_payload(model: int) -> bytes:
    payload = _payload(model=model, battery=75, temp_c=20.0)
    _le16(payload, 10, 11, 32767 + 1000)  # left 10.00 kg
    _le16(payload, 12, 13, 32767 + 1050)  # right 10.50 kg
    payload[14] = 50  # humidity, ignored by model 49
    _le16(payload, 15, 16, 32767 + 950)  # left 2 9.50 kg
    _le16(payload, 17, 18, 32767 + 975)  # right 2 9.75 kg
    _le16(payload, 19, 20, 32767 + 3975)  # realtime total 39.75 kg
    return bytes(payload)


def _t_payload(swarm_time_unix: int = int(SWARM_TIME.timestamp()), swarm_state: int = 2) -> bytes:
    payload = _payload(model=47, battery=70, temp_c=12.34)
    payload[15:19] = swarm_time_unix.to_bytes(4, "little")
    payload[19] = swarm_state  # swarm state
    return bytes(payload)


def _service_info(
    address: str, payload: bytes, manufacturer_id: int = MANUFACTURER_ID
) -> BluetoothServiceInfoBleak:
    manufacturer_data = {manufacturer_id: payload}
    return BluetoothServiceInfoBleak(
        name=address,
        address=address,
        rssi=-60,
        manufacturer_data=manufacturer_data,
        service_data={},
        service_uuids=[],
        source="local",
        device=BLEDevice(address, None, None),
        advertisement=AdvertisementData(
            local_name=None,
            manufacturer_data=manufacturer_data,
            service_data={},
            service_uuids=[],
            tx_power=None,
            rssi=-60,
            platform_data=(),
        ),
        connectable=True,
        time=time.monotonic(),
        tx_power=None,
    )


def _inject(hass: HomeAssistant, address: str, payload: bytes) -> None:
    """Hand an advertisement to HA's bluetooth manager as if a local adapter received it."""
    _get_manager(hass).scanner_adv_received(_service_info(address, payload))


def _entry_for(hass: HomeAssistant, address: str) -> ConfigEntry | None:
    return next(
        (e for e in hass.config_entries.async_entries(DOMAIN) if e.unique_id == address), None
    )


def _device_for(device_registry: dr.DeviceRegistry, address: str) -> dr.DeviceEntry | None:
    # The bluetooth processor entity replaces our identifiers, so look up by connection
    return device_registry.async_get_device(connections={(dr.CONNECTION_BLUETOOTH, address)})


async def test_GIVEN_three_broodminders_WHEN_discovered_THEN_entries_devices_and_sensors_created(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Verifies discovery creates one loaded entry per device, with a named device and sensors."""

    _inject(hass, TH_ADDRESS, _th_payload())
    _inject(hass, SCALE_ADDRESS, _scale_payload())
    _inject(hass, T_ADDRESS, _t_payload())
    await hass.async_block_till_done(wait_background_tasks=True)

    # One config entry per device, all loaded
    entries = hass.config_entries.async_entries(DOMAIN)
    assert {e.unique_id for e in entries} == {TH_ADDRESS, SCALE_ADDRESS, T_ADDRESS}
    assert all(e.state is ConfigEntryState.LOADED for e in entries)

    # Second round of adverts: the coordinators are now listening and create entities
    _inject(hass, TH_ADDRESS, _th_payload())
    _inject(hass, SCALE_ADDRESS, _scale_payload())
    _inject(hass, T_ADDRESS, _t_payload())
    await hass.async_block_till_done(wait_background_tasks=True)

    # Devices are named after the model and the last octets of the MAC
    for address, model, name in (
        (TH_ADDRESS, "TH", "BroodMinder-TH 00:00:01"),
        (SCALE_ADDRESS, "Scale W", "BroodMinder-Scale W 00:00:02"),
        (T_ADDRESS, "T", "BroodMinder-T 00:00:03"),
    ):
        device = _device_for(device_registry, address)
        assert device is not None, address
        assert device.name == name
        assert device.model == model
        assert device.manufacturer == MANUFACTURER
        assert device.sw_version == "1.2"

    # TH model reports temperature, humidity and battery
    th = "sensor.broodminder_th_00_00_01"
    assert float(hass.states.get(f"{th}_temperature").state) == 25.0
    assert hass.states.get(f"{th}_temperature").attributes["unit_of_measurement"] == "°C"
    assert hass.states.get(f"{th}_humidity").state == "55"
    assert hass.states.get(f"{th}_battery").state == "90"
    assert hass.states.get(f"{th}_sample_count").state == "1234"
    assert hass.states.get(f"{th}_weight_left") is None

    # Scale W: weights, but unconnected second channels are not created
    scale = "sensor.broodminder_scale_w_00_00_02"
    assert float(hass.states.get(f"{scale}_weight_left").state) == 20.0
    assert float(hass.states.get(f"{scale}_weight_right").state) == 21.5
    assert float(hass.states.get(f"{scale}_weight_realtime").state) == 41.5
    assert hass.states.get(f"{scale}_weight_left").attributes["unit_of_measurement"] == "kg"
    assert hass.states.get(f"{scale}_weight_left_2") is None
    assert hass.states.get(f"{scale}_weight_right_2") is None

    # T: no humidity, but swarm state and swarm time
    t = "sensor.broodminder_t_00_00_03"
    assert float(hass.states.get(f"{t}_temperature").state) == 12.34
    assert hass.states.get(f"{t}_humidity") is None
    assert hass.states.get(f"{t}_swarm_state").state == "2"
    assert (
        hass.states.get(f"{t}_swarm_state").attributes["description"]
        == "Stopped - by stop request"
    )
    assert "description" not in hass.states.get(f"{t}_temperature").attributes
    assert hass.states.get(f"{t}_swarm_time").state == SWARM_TIME.isoformat()

    # Sensors of one device don't leak into another
    th_device = _device_for(device_registry, TH_ADDRESS)
    scale_device = _device_for(device_registry, SCALE_ADDRESS)
    assert th_device.id != scale_device.id


async def test_GIVEN_configured_broodminder_WHEN_advertising_again_THEN_no_duplicate_entry(
    hass: HomeAssistant,
) -> None:
    """Verifies repeat adverts from a known device don't create another entry or flow."""

    _inject(hass, TH_ADDRESS, _th_payload())
    await hass.async_block_till_done(wait_background_tasks=True)
    _inject(hass, TH_ADDRESS, _th_payload())
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []

    # A discovery for the same address is aborted
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=_service_info(TH_ADDRESS, _th_payload()),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_GIVEN_other_vendor_advert_WHEN_discovery_started_THEN_aborts_not_broodminder(
    hass: HomeAssistant,
) -> None:
    """Verifies the flow rejects advertisements without BroodMinder manufacturer data."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=_service_info(TH_ADDRESS, _th_payload(), manufacturer_id=OTHER_VENDOR_ID),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_broodminder"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_GIVEN_loaded_entry_WHEN_unloaded_THEN_sensors_unavailable(
    hass: HomeAssistant,
) -> None:
    """Verifies an entry unloads cleanly and its sensors stop reporting."""

    _inject(hass, TH_ADDRESS, _th_payload())
    await hass.async_block_till_done(wait_background_tasks=True)
    _inject(hass, TH_ADDRESS, _th_payload())
    await hass.async_block_till_done(wait_background_tasks=True)

    entry = _entry_for(hass, TH_ADDRESS)
    assert entry is not None
    assert hass.states.get("sensor.broodminder_th_00_00_01_temperature").state == "25.0"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]
    assert hass.states.get("sensor.broodminder_th_00_00_01_temperature").state == "unavailable"


async def _setup_device(hass: HomeAssistant, address: str, payload: bytes) -> None:
    """Discover a device, then advertise again so its entities are created."""
    _inject(hass, address, payload)
    await hass.async_block_till_done(wait_background_tasks=True)
    _inject(hass, address, payload)
    await hass.async_block_till_done(wait_background_tasks=True)


async def _setup_t_sensor(hass: HomeAssistant, payload: bytes) -> None:
    """Discover the T sensor, then advertise again so its entities are created."""
    await _setup_device(hass, T_ADDRESS, payload)


def _sensors_of(hass: HomeAssistant, prefix: str) -> set[str]:
    """Return the sensor names of one device, without its entity id prefix."""
    return {
        entity_id.removeprefix(f"{prefix}_")
        for entity_id in hass.states.async_entity_ids("sensor")
        if entity_id.startswith(f"{prefix}_")
    }


async def test_GIVEN_scale_w_43_WHEN_advertising_THEN_only_sent_values_and_calculated_total(
    hass: HomeAssistant,
) -> None:
    """Verifies model 43 gets its weights and a calculated total, without realtime sensors."""

    await _setup_device(hass, SCALE_W_43_ADDRESS, _scale_w_43_payload())

    scale = "sensor.broodminder_scale_w_00_00_04"
    assert _sensors_of(hass, scale) == {
        "battery",
        "humidity",
        "sample_count",
        "temperature",
        "weight_left",
        "weight_right",
        "weight_realtime",
    }
    assert round(float(hass.states.get(f"{scale}_temperature").state), 2) == 23.69
    assert float(hass.states.get(f"{scale}_weight_left").state) == 0.0
    assert float(hass.states.get(f"{scale}_weight_right").state) == 0.06
    assert float(hass.states.get(f"{scale}_weight_realtime").state) == 0.12


@pytest.mark.parametrize(
    ("model", "prefix", "has_humidity"),
    [
        (49, "sensor.broodminder_scale_w3_w4_00_00_05", False),
        (57, "sensor.broodminder_scale_w_00_00_05", True),
        (58, "sensor.broodminder_diy_00_00_05", True),
    ],
)
async def test_GIVEN_scale_with_extra_channels_WHEN_advertising_THEN_all_weight_sensors_created(
    hass: HomeAssistant, model: int, prefix: str, has_humidity: bool
) -> None:
    """Verifies scales with extra channels get all four weights and the realtime total."""

    await _setup_device(hass, EXTRA_CHANNELS_ADDRESS, _extra_channels_payload(model))

    expected = {
        "battery",
        "realtime_temp",
        "sample_count",
        "temperature",
        "weight_left",
        "weight_right",
        "weight_left_2",
        "weight_right_2",
        "weight_realtime",
    }
    if has_humidity:
        expected.add("humidity")
    assert _sensors_of(hass, prefix) == expected
    assert float(hass.states.get(f"{prefix}_weight_left").state) == 10.0
    assert float(hass.states.get(f"{prefix}_weight_right").state) == 10.5
    assert float(hass.states.get(f"{prefix}_weight_left_2").state) == 9.5
    assert float(hass.states.get(f"{prefix}_weight_right_2").state) == 9.75
    assert float(hass.states.get(f"{prefix}_weight_realtime").state) == 39.75
    assert hass.states.get(f"{prefix}_weight_left").attributes["unit_of_measurement"] == "kg"


async def test_GIVEN_t_sensor_with_unsynced_clock_WHEN_advertising_THEN_swarm_time_unknown(
    hass: HomeAssistant,
) -> None:
    """Verifies a swarm time counted from boot shows as unknown rather than a 1970 date."""

    await _setup_t_sensor(hass, _t_payload(swarm_time_unix=3600))  # one hour after boot

    state = hass.states.get("sensor.broodminder_t_00_00_03_swarm_time")
    assert state is not None
    assert state.state == "unknown"


async def test_GIVEN_valid_swarm_time_WHEN_uptime_value_arrives_THEN_swarm_time_unknown(
    hass: HomeAssistant,
) -> None:
    """Verifies a synced swarm time is replaced, not kept, when the clock is reset."""

    await _setup_t_sensor(hass, _t_payload())
    swarm_time = "sensor.broodminder_t_00_00_03_swarm_time"
    assert hass.states.get(swarm_time).state == SWARM_TIME.isoformat()

    # Battery change: the clock restarts from boot until the next Bees app sync
    _inject(hass, T_ADDRESS, _t_payload(swarm_time_unix=3600))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(swarm_time).state == "unknown"


async def test_GIVEN_swarm_state_WHEN_advertising_THEN_state_is_code_with_description(
    hass: HomeAssistant,
) -> None:
    """Verifies the swarm state stays numeric and gets a readable description attribute."""

    await _setup_t_sensor(hass, _t_payload(swarm_state=29))  # swarm event detected

    state = hass.states.get("sensor.broodminder_t_00_00_03_swarm_state")
    assert state is not None
    assert state.state == "29"
    assert state.attributes["description"] == "Swarm event detected"


async def test_GIVEN_th_sensor_WHEN_too_short_advertisement_arrives_THEN_sensors_keep_values(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Verifies an advertisement too short to parse is ignored without errors."""

    await _setup_device(hass, TH_ADDRESS, _th_payload())
    temperature = "sensor.broodminder_th_00_00_01_temperature"
    assert hass.states.get(temperature).state == "25.0"

    short_payload = bytes(
        [
            56,  # [0] model TH
            2,  # [1] v.minor
            1,  # [2] v.major
            0,  # [3] realtime temperature LSB; battery at [4] is missing
        ]
    )
    _inject(hass, TH_ADDRESS, short_payload)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(temperature).state == "25.0"
    assert "Unexpected error" not in caplog.text


TH_BATTERY = "sensor.broodminder_th_00_00_01_battery"


def _th_battery_payload(battery: int) -> bytes:
    """Return the TH's advertisement with a battery byte: battery % or 100 + charge / 4."""
    payload = _payload(model=56, battery=battery, temp_c=25.0)
    payload[14] = 55  # humidity
    return bytes(payload)


async def _advertise(hass: HomeAssistant, address: str, payload: bytes) -> None:
    _inject(hass, address, payload)
    await hass.async_block_till_done(wait_background_tasks=True)


def _battery(hass: HomeAssistant) -> tuple[str, int | None, int | None]:
    """Return the TH's battery level and the voltage based and charge remaining readings."""
    state = hass.states.get(TH_BATTERY)
    return (state.state, state.attributes["voltage_based"], state.attributes["charge_remaining"])


async def test_GIVEN_th_sensor_WHEN_battery_readings_alternate_THEN_battery_is_lower_reading(
    hass: HomeAssistant,
) -> None:
    """Verifies one Battery entity shows the lower of the last reading of each kind."""

    # Voltage based reading only
    await _setup_device(hass, TH_ADDRESS, _th_battery_payload(battery=90))
    assert _battery(hass) == ("90", 90, None)
    state = hass.states.get(TH_BATTERY)
    assert state.attributes["unit_of_measurement"] == "%"
    assert state.attributes["device_class"] == "battery"
    assert state.attributes["state_class"] == "measurement"
    assert "charge_remaining" not in _sensors_of(hass, "sensor.broodminder_th_00_00_01")

    # Charge remaining 100 + 40 / 4 is lower
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=110))
    assert _battery(hass) == ("40", 90, 40)

    # A lower voltage based reading that is still above the charge remaining
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=80))
    assert _battery(hass) == ("40", 80, 40)

    # The voltage based reading drops below the charge remaining, as on a cold night
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=30))
    assert _battery(hass) == ("30", 30, 40)

    # Invalid value above 125: nothing changes
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=200))
    assert _battery(hass) == ("30", 30, 40)

    # Byte 100 is a voltage based reading
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=100))
    assert _battery(hass) == ("40", 100, 40)


async def test_GIVEN_voltage_readings_only_WHEN_voltage_goes_down_and_up_THEN_battery_follows(
    hass: HomeAssistant,
) -> None:
    """Verifies Battery follows the voltage down and up on firmware without charge remaining."""

    await _setup_device(hass, TH_ADDRESS, _th_battery_payload(battery=90))
    assert _battery(hass) == ("90", 90, None)

    # Down, as on a cold night or with a battery running low
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=30))
    assert _battery(hass) == ("30", 30, None)

    # Up again, as when it warms up or after a battery change
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=95))
    assert _battery(hass) == ("95", 95, None)


async def test_GIVEN_no_battery_entity_yet_WHEN_reading_arrives_THEN_battery_shows_it_at_once(
    hass: HomeAssistant,
) -> None:
    """Verifies the advertisement that creates Battery is used, though it isn't repeated."""

    await _setup_device(hass, TH_ADDRESS, _th_battery_payload(battery=200))  # invalid
    assert hass.states.get(TH_BATTERY) is None

    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=90))

    assert _battery(hass) == ("90", 90, None)


async def test_GIVEN_battery_readings_WHEN_entry_reloaded_THEN_both_kept(
    hass: HomeAssistant,
) -> None:
    """Verifies a reload keeps both readings, not only the one advertised last."""

    await _setup_device(hass, TH_ADDRESS, _th_battery_payload(battery=90))
    await _advertise(hass, TH_ADDRESS, _th_battery_payload(battery=110))
    entry = _entry_for(hass, TH_ADDRESS)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _battery(hass) == ("40", 90, 40)


async def test_GIVEN_restored_battery_readings_WHEN_voltage_reading_arrives_THEN_charge_kept(
    hass: HomeAssistant,
) -> None:
    """Verifies the readings from before a restart are restored and combined with new ones."""

    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(TH_BATTERY, "40", {"voltage_based": 80, "charge_remaining": 40}),
                {"voltage_based": 80, "charge_remaining": 40},
            )
        ],
    )

    await _setup_device(hass, TH_ADDRESS, _th_battery_payload(battery=90))

    assert _battery(hass) == ("40", 90, 40)


async def test_GIVEN_unusable_restored_battery_readings_WHEN_reading_arrives_THEN_ignored(
    hass: HomeAssistant,
) -> None:
    """Verifies restored values that aren't whole numbers are left out."""

    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(TH_BATTERY, "40"),
                {"voltage_based": "80", "charge_remaining": True},
            )
        ],
    )

    await _setup_device(hass, TH_ADDRESS, _th_battery_payload(battery=90))

    assert _battery(hass) == ("90", 90, None)


TH_BROOD = "sensor.broodminder_th_00_00_01_brood"
T_BROOD = "sensor.broodminder_t_00_00_03_brood"
OUTDOOR_SENSOR = "sensor.outdoor"
OUTDOOR_FAHRENHEIT = {"unit_of_measurement": "°F", "device_class": "temperature"}
WEATHER_ATTRIBUTES = {"temperature": 18.0, "temperature_unit": "°C"}
SAMPLES_PER_HOUR = 12


async def _setup_hive(
    hass: HomeAssistant, options: dict[str, str] | None = None
) -> MockConfigEntry:
    """Set up the TH hive's entry as discovery creates it, with brood settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TH_ADDRESS,
        title=f"BroodMinder {TH_ADDRESS}",
        data={CONF_MODEL: 56},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _pass_time(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    samples: int,
    hive_c: float | None = None,
) -> None:
    """Move time on by a number of brood samples, with the TH hive advertising hive_c."""
    for _ in range(samples):
        if hive_c is not None:
            _inject(hass, TH_ADDRESS, _th_payload(temp_c=hive_c))
        freezer.tick(BROOD_SAMPLE_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


async def _run_due_timers(hass: HomeAssistant) -> None:
    """Run timers that are due now, such as a scheduled save, without moving time on."""
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_GIVEN_t_and_scale_WHEN_discovered_THEN_only_t_gets_brood_sensor_and_settings(
    hass: HomeAssistant,
) -> None:
    """Verifies only models measuring in-hive temperature get a brood estimate."""

    await _setup_device(hass, T_ADDRESS, _t_payload())
    await _setup_device(hass, SCALE_ADDRESS, _scale_payload())

    t_entry = _entry_for(hass, T_ADDRESS)
    scale_entry = _entry_for(hass, SCALE_ADDRESS)
    assert t_entry.data == {CONF_MODEL: 47}
    assert t_entry.supports_options
    assert not scale_entry.supports_options
    assert hass.states.get(T_BROOD) is not None
    assert "brood" not in _sensors_of(hass, "sensor.broodminder_scale_w_00_00_02")


async def test_GIVEN_only_a_scale_WHEN_no_weather_entity_THEN_no_repair(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Verifies a scale, which has no brood estimate, doesn't ask for an outdoor temperature."""

    await _setup_device(hass, SCALE_ADDRESS, _scale_payload())

    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is None


async def test_GIVEN_hive_WHEN_brood_settings_saved_THEN_hive_reloads_with_them(
    hass: HomeAssistant,
) -> None:
    """Verifies the settings dialog stores the sensor position and outdoor temperature."""

    entry = await _setup_hive(hass)
    settings = {CONF_SENSOR_POSITION: POSITION_IN_COMB, CONF_OUTDOOR_ENTITY: OUTDOOR_SENSOR}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=settings
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == settings
    attributes = hass.states.get(TH_BROOD).attributes
    assert attributes["sensor_position"] == POSITION_IN_COMB
    assert attributes["outdoor_entity"] == OUTDOOR_SENSOR


async def test_GIVEN_no_weather_entity_WHEN_hive_set_up_THEN_brood_unknown_and_repair_raised(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Verifies a missing outdoor temperature shows on the sensor and as a repair."""

    await _setup_hive(hass)

    state = hass.states.get(TH_BROOD)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["status"] == "no_outdoor_temperature"
    assert state.attributes["outdoor_entity"] is None
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is not None


async def test_GIVEN_no_weather_repair_WHEN_weather_entity_added_THEN_used_and_repair_gone(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, issue_registry: ir.IssueRegistry
) -> None:
    """Verifies a new weather entity is picked up at the next sample, without a restart."""

    await _setup_hive(hass)
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is not None

    hass.states.async_set("weather.home", "sunny", WEATHER_ATTRIBUTES)
    await _pass_time(hass, freezer, 1)

    state = hass.states.get(TH_BROOD)
    assert state.attributes["outdoor_entity"] == "weather.home"
    assert state.attributes["status"] == "not_enough_data"
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is None


async def test_GIVEN_no_weather_repair_WHEN_hive_unloaded_THEN_repair_gone(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Verifies the repair doesn't outlive the last hive that needs a weather entity."""

    entry = await _setup_hive(hass)
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is None


async def test_GIVEN_met_home_and_other_weather_WHEN_hive_set_up_THEN_met_home_used(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Verifies Met.no's Forecast Home is preferred over other weather entities."""

    entity_registry.async_get_or_create(
        "weather", "met", "home", suggested_object_id="forecast_home"
    )
    hass.states.async_set("weather.forecast_home", "sunny", WEATHER_ATTRIBUTES)
    hass.states.async_set("weather.other", "rainy", WEATHER_ATTRIBUTES)

    await _setup_hive(hass)

    assert hass.states.get(TH_BROOD).attributes["outdoor_entity"] == "weather.forecast_home"


async def test_GIVEN_several_weather_entities_without_met_home_WHEN_set_up_THEN_repair_raised(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Verifies the integration doesn't guess between weather entities."""

    hass.states.async_set("weather.one", "sunny", WEATHER_ATTRIBUTES)
    hass.states.async_set("weather.two", "rainy", WEATHER_ATTRIBUTES)

    await _setup_hive(hass)

    assert hass.states.get(TH_BROOD).attributes["outdoor_entity"] is None
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is not None


async def test_GIVEN_hive_held_at_35_WHEN_hours_pass_THEN_brood_estimated_and_kept_on_reload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Verifies the estimate from advertisements and an outdoor sensor in °F, end to end."""

    freezer.move_to("2026-06-01T12:02:00+00:00")
    # 59 °F is 15 °C; read as 59 °C it would be too hot to give an estimate
    hass.states.async_set(OUTDOOR_SENSOR, "59", OUTDOOR_FAHRENHEIT)
    entry = await _setup_hive(hass, {CONF_OUTDOOR_ENTITY: OUTDOOR_SENSOR})

    await _pass_time(hass, freezer, 17 * SAMPLES_PER_HOUR, hive_c=35.0)
    state = hass.states.get(TH_BROOD)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["status"] == "not_enough_data"

    await _pass_time(hass, freezer, 3 * SAMPLES_PER_HOUR, hive_c=35.0)
    state = hass.states.get(TH_BROOD)
    assert state.state == "100"
    assert state.attributes["status"] == "ok"
    assert state.attributes["hours_used"] == 20

    # The hours are stored, so the estimate is back right after a reload
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(TH_BROOD).state == "100"


async def test_GIVEN_outdoor_sensor_unavailable_WHEN_3_hours_pass_THEN_repair_until_back(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, issue_registry: ir.IssueRegistry
) -> None:
    """Verifies a chosen outdoor sensor that stays unavailable raises a repair for the hive."""

    hass.states.async_set(OUTDOOR_SENSOR, STATE_UNAVAILABLE)
    entry = await _setup_hive(hass, {CONF_OUTDOOR_ENTITY: OUTDOOR_SENSOR})
    issue_id = f"{ISSUE_OUTDOOR_UNAVAILABLE}_{entry.entry_id}"

    await _pass_time(hass, freezer, 3 * SAMPLES_PER_HOUR - 1)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None
    assert hass.states.get(TH_BROOD).attributes["status"] == "no_outdoor_temperature"

    await _pass_time(hass, freezer, 1)
    issue = issue_registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_placeholders == {
        "hive": "BroodMinder-TH 00:00:01",
        "entity_id": OUTDOOR_SENSOR,
    }

    hass.states.async_set(OUTDOOR_SENSOR, "59", OUTDOOR_FAHRENHEIT)
    await _pass_time(hass, freezer, 1)
    assert issue_registry.async_get_issue(DOMAIN, issue_id) is None


async def test_GIVEN_entry_from_before_brood_WHEN_t_advertises_THEN_brood_sensor_added(
    hass: HomeAssistant,
) -> None:
    """Verifies an entry without a stored model learns it and gets its brood sensor."""

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=T_ADDRESS, title=f"BroodMinder {T_ADDRESS}", data={}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not entry.supports_options
    assert hass.states.get(T_BROOD) is None

    _inject(hass, T_ADDRESS, _t_payload())
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.data == {CONF_MODEL: 47}
    assert hass.states.get(T_BROOD) is not None


async def test_GIVEN_hive_with_stored_hours_WHEN_removed_THEN_brood_history_deleted(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Verifies removing a hive doesn't leave its brood history behind."""

    entry = await _setup_hive(hass)
    storage_key = f"{DOMAIN}.brood.{entry.entry_id}"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert storage_key in hass_storage  # saved when the hive unloads

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert storage_key not in hass_storage


async def test_GIVEN_hive_sampling_WHEN_hour_completes_THEN_hours_stored_without_unload(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    """Verifies the hours are stored every hour, so a crash loses at most the hour in progress."""

    freezer.move_to("2026-06-01T12:02:00+00:00")
    hass.states.async_set(OUTDOOR_SENSOR, "59", OUTDOOR_FAHRENHEIT)
    entry = await _setup_hive(hass, {CONF_OUTDOOR_ENTITY: OUTDOOR_SENSOR})
    storage_key = f"{DOMAIN}.brood.{entry.entry_id}"
    await _run_due_timers(hass)
    hass_storage.pop(storage_key)  # stored when sampling starts in a new hour

    await _pass_time(hass, freezer, 11, hive_c=35.0)  # 12:57, still the same hour
    await _run_due_timers(hass)
    assert storage_key not in hass_storage

    await _pass_time(hass, freezer, 1, hive_c=35.0)  # 13:02, the 12:00 hour is complete
    await _run_due_timers(hass)
    completed_hour = hass_storage[storage_key]["data"][0]
    assert completed_hour["hour"] == datetime(2026, 6, 1, 12, tzinfo=UTC).timestamp()
    assert completed_hour["hive_count"] == 11  # 12:07 to 12:57
    assert completed_hour["outdoor_count"] == 12  # 12:02 to 12:57


async def test_GIVEN_hour_in_progress_WHEN_home_assistant_stops_THEN_hours_stored(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    """Verifies a restart keeps the samples of the hour in progress, without an unload."""

    freezer.move_to("2026-06-01T12:02:00+00:00")
    hass.states.async_set(OUTDOOR_SENSOR, "59", OUTDOOR_FAHRENHEIT)
    entry = await _setup_hive(hass, {CONF_OUTDOOR_ENTITY: OUTDOOR_SENSOR})
    storage_key = f"{DOMAIN}.brood.{entry.entry_id}"
    await _pass_time(hass, freezer, 5, hive_c=35.0)  # 12:27
    await _run_due_timers(hass)
    hass_storage.pop(storage_key)  # stored when sampling started in a new hour

    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()

    hour_in_progress = hass_storage[storage_key]["data"][-1]
    assert hour_in_progress["hour"] == datetime(2026, 6, 1, 12, tzinfo=UTC).timestamp()
    assert hour_in_progress["hive_count"] == 5  # 12:07 to 12:27
    assert hour_in_progress["outdoor_count"] == 6  # 12:02 to 12:27


async def test_GIVEN_stored_hours_WHEN_home_assistant_starting_THEN_estimate_shown_at_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    """Verifies a restart shows the stored estimate before the first sample."""

    freezer.move_to("2026-06-01T12:02:00+00:00")
    current_hour = int(datetime(2026, 6, 1, 12, tzinfo=UTC).timestamp())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TH_ADDRESS,
        title=f"BroodMinder {TH_ADDRESS}",
        data={CONF_MODEL: 56},
        options={CONF_OUTDOOR_ENTITY: OUTDOOR_SENSOR},
    )
    entry.add_to_hass(hass)
    storage_key = f"{DOMAIN}.brood.{entry.entry_id}"
    hass_storage[storage_key] = {
        "version": 1,
        "minor_version": 1,
        "key": storage_key,
        "data": [
            {
                "hour": current_hour - offset * 3600,
                "hive_sum": 35.0 * SAMPLES_PER_HOUR,
                "hive_count": SAMPLES_PER_HOUR,
                "outdoor_sum": 15.0 * SAMPLES_PER_HOUR,
                "outdoor_count": SAMPLES_PER_HOUR,
            }
            for offset in range(24, 0, -1)
        ],
    }
    hass.set_state(CoreState.starting)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(TH_BROOD)
    assert state.state == "100"
    assert state.attributes["status"] == "ok"
    assert state.attributes["hours_used"] == 24

    # The first sample finds no outdoor temperature yet, but the stored hours still count
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    state = hass.states.get(TH_BROOD)
    assert state.state == "100"
    assert state.attributes["status"] == "ok"
