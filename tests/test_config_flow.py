"""End-to-end tests: fake BLE advertisements → discovery → config entries → sensor entities."""

# ruff: noqa: PLR2004

from datetime import UTC, datetime
import time

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, _get_manager
from homeassistant.config_entries import SOURCE_BLUETOOTH, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
import pytest

from custom_components.broodminder.const import DOMAIN, MANUFACTURER, MANUFACTURER_ID

pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "enable_bluetooth")

TH_ADDRESS = "AA:BB:CC:00:00:01"
SCALE_ADDRESS = "AA:BB:CC:00:00:02"
T_ADDRESS = "AA:BB:CC:00:00:03"
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


def _th_payload() -> bytes:
    payload = _payload(model=56, battery=90, temp_c=25.0)
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


def _t_payload(swarm_time_unix: int = int(SWARM_TIME.timestamp())) -> bytes:
    payload = _payload(model=47, battery=70, temp_c=12.34)
    payload[15:19] = swarm_time_unix.to_bytes(4, "little")
    payload[19] = 2  # swarm state
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


async def _setup_t_sensor(hass: HomeAssistant, payload: bytes) -> None:
    """Discover the T sensor, then advertise again so its entities are created."""
    _inject(hass, T_ADDRESS, payload)
    await hass.async_block_till_done(wait_background_tasks=True)
    _inject(hass, T_ADDRESS, payload)
    await hass.async_block_till_done(wait_background_tasks=True)


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
