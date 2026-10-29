"""Tests for broodminder/sensor.py."""

from custom_components.broodminder.ble_parser import parse_manufacturer_data
from custom_components.broodminder.const import MANUFACTURER, MANUFACTURER_ID
from custom_components.broodminder.sensor import sensor_update_to_bluetooth_data_update


def test_GIVEN_model_th_WHEN_build_update_THEN_device_model_is_model_name() -> None:
    """Verifies the device info shows the model name instead of the numeric model id."""

    payload = bytearray(15)
    payload[0] = 56  # model
    payload[1] = 2  # v.minor
    payload[2] = 1  # v.major

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("11:22:33:44:55:66", adv)
    assert parsed is not None

    update = sensor_update_to_bluetooth_data_update(parsed)
    device = update.devices[parsed.device_id]

    assert device["model"] == "TH"
    assert device["name"] == "BroodMinder-TH 44:55:66"
    assert device["manufacturer"] == MANUFACTURER
    assert device["sw_version"] == "1.2"
