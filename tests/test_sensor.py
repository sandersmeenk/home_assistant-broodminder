"""Tests for broodminder/sensor.py."""
# ruff: noqa: PLR2004

import pytest

from custom_components.broodminder.ble_parser import parse_manufacturer_data
from custom_components.broodminder.const import (
    MANUFACTURER,
    MANUFACTURER_ID,
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
from custom_components.broodminder.sensor import (
    sensor_update_to_bluetooth_data_update,
    swarm_state_description,
)


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


def test_GIVEN_scale_w_57_WHEN_build_update_THEN_temperature_and_weight_have_precision() -> None:
    """Verifies temperature and weight sensors suggest a display precision."""

    raw_temp = 0x1D4C  # 7500 -> 25.00 °C
    payload = bytearray(21)
    payload[0] = 57  # model
    payload[1] = 2  # v.minor
    payload[2] = 1  # v.major
    payload[3] = raw_temp & 0xFF  # realtime temperature LSB
    payload[4] = 80  # battery %
    payload[7] = raw_temp & 0xFF  # temperature LSB
    payload[8] = (raw_temp >> 8) & 0xFF  # temperature MSB
    payload[9] = (raw_temp >> 8) & 0xFF  # realtime temperature MSB
    payload[10] = 0xD1  # weight left LSB: 12.34 kg -> 32767 + 1234 = 0x84D1
    payload[11] = 0x84  # weight left MSB
    payload[12] = 0xF3  # weight right LSB: 5.00 kg -> 32767 + 500 = 0x81F3
    payload[13] = 0x81  # weight right MSB
    payload[15] = 0xD1  # weight left 2 LSB
    payload[16] = 0x84  # weight left 2 MSB
    payload[17] = 0xF3  # weight right 2 LSB
    payload[18] = 0x81  # weight right 2 MSB
    payload[19] = 0xCF  # realtime total LSB: 20.00 kg -> 32767 + 2000 = 0x87CF
    payload[20] = 0x87  # realtime total MSB

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("11:22:33:44:55:66", adv)
    assert parsed is not None

    update = sensor_update_to_bluetooth_data_update(parsed)
    precisions = {
        key.key: description.suggested_display_precision
        for key, description in update.entity_descriptions.items()
    }

    assert precisions[SENSOR_TEMP] == 1
    assert precisions[SENSOR_TEMP_RT] == 1
    assert precisions[SENSOR_WEIGHT_L] == 2
    assert precisions[SENSOR_WEIGHT_R] == 2
    assert precisions[SENSOR_WEIGHT_L2] == 2
    assert precisions[SENSOR_WEIGHT_R2] == 2
    assert precisions[SENSOR_WEIGHT_REALTIME] == 2


@pytest.mark.parametrize(
    ("swarm_state", "expected"),
    [
        (0, "Stopped"),
        (29, "Swarm event detected"),
        (61, "Swarm event logging complete - still waiting"),
        (0xCF, "Unknown"),  # not a documented SwarmMinder state
    ],
)
def test_GIVEN_swarm_state_code_WHEN_describe_THEN_readable_description(
    swarm_state: int, expected: str
) -> None:
    """Verifies swarm state codes map to their documented description, or Unknown."""

    assert swarm_state_description(swarm_state) == expected


def test_GIVEN_all_documented_swarm_states_WHEN_describe_THEN_each_has_own_description() -> None:
    """Verifies every documented code has a distinct description that isn't the fallback."""

    descriptions = [swarm_state_description(code) for code in SWARM_STATE_DESCRIPTIONS]

    assert SWARM_STATE_DESCRIPTION_UNKNOWN not in descriptions
    assert len(set(descriptions)) == len(SWARM_STATE_DESCRIPTIONS)
