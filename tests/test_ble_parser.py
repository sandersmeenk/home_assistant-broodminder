"""Tests for broodminder/ble_parser.py."""

# ruff: noqa: PLR2004

import datetime
import math

import pytest

from custom_components.broodminder.ble_parser import extract_entities, parse_manufacturer_data
from custom_components.broodminder.const import (
    MANUFACTURER_ID,
    SENSOR_BATT,
    SENSOR_HUM,
    SENSOR_SAMPLE_COUNT,
    # Optional extras we don't strictly assert in values, but we verify presence/absence
    # (left here in case you later want to assert on them)
    # SENSOR_TEMP_RT1,
    # SENSOR_TEMP_RT2,
    # SENSOR_WEIGHT_L2,
    # SENSOR_WEIGHT_R2,
    SENSOR_SWARM_STATE,
    SENSOR_SWARM_TIME,
    SENSOR_TEMP,
    SENSOR_WEIGHT_L,
    SENSOR_WEIGHT_R,
    SENSOR_WEIGHT_REALTIME,
)


def test_GIVEN_invalid_payload__WHEN_parse_THEN_returns_none() -> None:
    """Verifies an advertisement with invalid manufacturer id."""

    parsed = parse_manufacturer_data("AA", {MANUFACTURER_ID: b"\x00\x01"})
    assert parsed is None


@pytest.mark.parametrize(
    ("model_id", "model_name"),
    [
        (41, "T"),
        (47, "T"),
        (42, "TH"),
        (56, "TH"),
        (43, "Scale W"),
        (57, "Scale W"),
        (49, "Scale W3/W4"),
        (52, "SubHub"),
        (54, "Hub 4G"),
        (58, "DIY"),
        (60, "Hub Wifi"),
        (63, "BeeDar"),
    ],
)
def test_GIVEN_known_model_id_WHEN_parse_THEN_reports_model_name(
    model_id: int, model_name: str
) -> None:
    """Verifies the numeric model id is mapped to its model name."""

    payload = bytearray(15)
    payload[0] = model_id  # model

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)

    assert parsed is not None
    assert parsed.model == model_id
    assert parsed.model_name == model_name
    assert parsed.device_name == f"BroodMinder-{model_name} DD:EE:FF"


def test_GIVEN_unknown_model_id_WHEN_parse_THEN_reports_unknown_model_name() -> None:
    """Verifies an unmapped model id falls back to "Unknown"."""

    payload = bytearray(15)
    payload[0] = 99  # model, not in ID_TO_MODEL

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)

    assert parsed is not None
    assert parsed.model == 99
    assert parsed.model_name == "Unknown"
    assert parsed.device_name == "BroodMinder-Unknown DD:EE:FF"


def test_GIVEN_model_t_WHEN_battery_above_100_THEN_reports_100() -> None:
    """Verifies an advertisement with battery above hundred."""

    payload = bytearray(15)
    payload[0] = 41  # model
    payload[1] = 0  # v.minor
    payload[2] = 0  # v.major
    payload[4] = 250  # battery %

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None
    assert parsed.model == 41
    assert parsed.battery_percent == 100

    entities = extract_entities(parsed)
    assert SENSOR_BATT in entities


def test_GIVEN_model_t_WHEN_battery_in_range_THEN_reports_battery() -> None:
    """Verifies an advertisement with battery above hundred."""

    payload = bytearray(15)
    payload[0] = 41  # model
    payload[1] = 0  # v.minor
    payload[2] = 0  # v.major
    payload[4] = 1  # battery %

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None
    assert parsed.model == 41
    assert parsed.battery_percent == 1

    entities = extract_entities(parsed)
    assert SENSOR_BATT in entities


def test_GIVEN_model_t_WHEN_parse_with_humidity_value_THEN_reports_no_humidity() -> None:
    """Verifies a temperature advertisement without humidity."""

    raw_temp = 0x8000  # 32768 -> ~42.5 C after conversion
    payload = bytearray(15)
    payload[0] = 41  # model
    payload[1] = 3  # v.minor
    payload[2] = 1  # v.major
    payload[4] = 88  # battery %
    payload[7] = raw_temp & 0xFF
    payload[8] = (raw_temp >> 8) & 0xFF
    payload[14] = 99  # would be ignored for this model

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None
    assert parsed.model == 41
    assert parsed.humidity_percent is None  # filtered out by model rules

    entities = extract_entities(parsed)
    assert SENSOR_HUM not in entities


def test_GIVEN_model_t_WHEN_parse_with_temperature_value_THEN_reports_temperature() -> None:
    """Verifies a temperature advertisement without humidity."""

    raw_temp = 0x8000  # 32768 -> ~42.5 C after conversion
    payload = bytearray(15)
    payload[0] = 41  # model
    payload[1] = 3  # v.minor
    payload[2] = 1  # v.major
    payload[4] = 88  # battery %
    payload[7] = raw_temp & 0xFF
    payload[8] = (raw_temp >> 8) & 0xFF
    payload[14] = 99  # would be ignored for this model

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)

    assert parsed is not None
    assert parsed.device_name == "BroodMinder-T DD:EE:FF"
    assert parsed.model == 41

    # approx 42.5 C
    assert parsed.temperature_c is not None
    assert math.isclose(parsed.temperature_c, 42.5, rel_tol=1e-3, abs_tol=1e-3)

    entities = extract_entities(parsed)
    assert SENSOR_TEMP in entities


def test_GIVEN_model_th_WHEN_parse_THEN_reports_temp_and_humidity() -> None:
    """Verifies an advertisement with temperature and humidity."""

    # Model 42 uses default centi-C with +5000 offset
    # raw = 0x1403 = 5123 -> (5123 - 5000)/100 = 1.23 C
    payload = bytearray(15)
    payload[0] = 56  # model
    payload[1] = 2
    payload[2] = 1
    payload[4] = 100  # battery %
    payload[7] = 0x03
    payload[8] = 0x14
    payload[14] = 55  # 55% RH

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("11:22:33:44:55:66", adv)

    assert parsed is not None
    assert parsed.device_name == "BroodMinder-TH 44:55:66"
    assert parsed.model == 56
    assert parsed.humidity_percent == 55
    assert parsed.temperature_c is not None
    assert abs(parsed.temperature_c - 1.23) < 1e-6


def test_parse_primary_extended_fields_model_th() -> None:
    """Validate the extra PRIMARY fields and their entities for model TH.

    Covers:
    - Elapsed seconds (bytes 15-16 overall → indices 5-6)
    - Weight L / Weight R (bytes 20-23 overall → indices 10-13)
    - Humidity (byte 24 → index 14)
    - SM time (bytes 25-28 → indices 15-18)
    - Realtime total weight (bytes 29-30 → indices 19-20)
    - Swarm state (byte 29 → index 19, raw).
    """
    payload = bytearray(21)  # we need up to index 20 inclusive
    # Header-ish
    payload[0] = 56  # model
    payload[1] = 2  # ver minor
    payload[2] = 1  # ver major

    # Battery %
    payload[4] = 100

    # Elapsed seconds: 0x1234 -> 4660 s (indices 5-6)
    payload[5] = 0x34
    payload[6] = 0x12

    # Primary temperature: raw 0x1403 = 5123 -> 1.23 C (indices 7-8)
    payload[7] = 0x03
    payload[8] = 0x14

    # Humidity 55% (index 14)
    payload[14] = 55

    # Weight Left: 12.34 kg -> raw = 32767 + 1234 = 34001 = 0x84D1 (indices 10-11)
    payload[10] = 0xD1  # low
    payload[11] = 0x84  # high

    # Weight Right: 5.00 kg -> raw = 32767 + 500 = 33267 = 0x81F3 (indices 12-13)
    payload[12] = 0xF3  # low
    payload[13] = 0x81  # high

    # SM time: choose 0x00FFFFFF (indices 15-18), while making L2/R2 sentinel -> None
    # (first pair 0xFFFF and second pair 0xFFFF are invalid weights)
    payload[15] = 0xFF
    payload[16] = 0xFF
    payload[17] = 0xFF
    payload[18] = 0x00  # little-endian => 0x00FFFFFF = 16777215

    # Realtime total weight / Swarm state:
    # Total weight 20.00 kg -> raw = 32767 + 2000 = 34767 = 0x87CF (indices 19-20)
    # Also means swarm_state byte (index 19) == 0xCF (207)
    payload[19] = 0xCF  # low / swarm_state
    payload[20] = 0x87  # high

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("22:33:44:55:66:77", adv)
    assert parsed is not None

    # Core fields
    assert parsed.device_name == "BroodMinder-TH 55:66:77"
    assert parsed.model == 56
    assert parsed.battery_percent == 100
    assert parsed.humidity_percent == 55
    assert parsed.temperature_c is not None
    assert abs(parsed.temperature_c - 1.23) < 1e-6

    # Extended fields
    assert parsed.elapsed_s == 0x1234
    assert parsed.weight_l_kg is None
    assert parsed.weight_r_kg is None
    assert parsed.weight_realtime_total_kg is None
    assert parsed.swarm_state_numeric == 0xCF
    assert parsed.swarm_time_supported is True
    assert parsed.swarm_time_utc is None  # 1970-07-14: time since boot, clock not synced

    # Verify entity export
    entities = extract_entities(parsed)
    assert entities[SENSOR_BATT] == 100
    assert entities[SENSOR_HUM] == 55
    assert math.isclose(entities[SENSOR_TEMP], 1.23, abs_tol=1e-6)
    assert entities[SENSOR_SAMPLE_COUNT] == 0x1234

    assert SENSOR_WEIGHT_L not in entities
    assert SENSOR_WEIGHT_R not in entities
    assert SENSOR_WEIGHT_REALTIME not in entities

    assert entities[SENSOR_SWARM_STATE] == 0xCF
    assert SENSOR_SWARM_TIME in entities
    assert entities[SENSOR_SWARM_TIME] is None


def test_parse_primary_extended_fields_model_w() -> None:
    """Validate the extra PRIMARY fields and their entities for model W.

    Covers:
    - Elapsed seconds (bytes 15-16 overall → indices 5-6)
    - Weight L / Weight R (bytes 20-23 overall → indices 10-13)
    - Humidity (byte 24 → index 14)
    - SM time (bytes 25-28 → indices 15-18)
    - Realtime total weight (bytes 29-30 → indices 19-20)
    - Swarm state (byte 29 → index 19, raw).
    """
    payload = bytearray(21)  # we need up to index 20 inclusive
    # Header-ish
    payload[0] = 57  # model
    payload[1] = 2  # ver minor
    payload[2] = 1  # ver major

    # Battery %
    payload[4] = 100

    # Elapsed seconds: 0x1234 -> 4660 s (indices 5-6)
    payload[5] = 0x34
    payload[6] = 0x12

    # Primary temperature: raw 0x1403 = 5123 -> 1.23 C (indices 7-8)
    payload[7] = 0x03
    payload[8] = 0x14

    # Humidity 55% (index 14)
    payload[14] = 55

    # Weight Left: 12.34 kg -> raw = 32767 + 1234 = 34001 = 0x84D1 (indices 10-11)
    payload[10] = 0xD1  # low
    payload[11] = 0x84  # high

    # Weight Right: 5.00 kg -> raw = 32767 + 500 = 33267 = 0x81F3 (indices 12-13)
    payload[12] = 0xF3  # low
    payload[13] = 0x81  # high

    # SM time: choose 0x00FFFFFF (indices 15-18), while making L2/R2 sentinel -> None
    # (first pair 0xFFFF and second pair 0xFFFF are invalid weights)
    payload[15] = 0xFF
    payload[16] = 0xFF
    payload[17] = 0xFF
    payload[18] = 0x00  # little-endian => 0x00FFFFFF = 16777215

    # Realtime total weight / Swarm state:
    # Total weight 20.00 kg -> raw = 32767 + 2000 = 34767 = 0x87CF (indices 19-20)
    # Also means swarm_state byte (index 19) == 0xCF (207)
    payload[19] = 0xCF  # low / swarm_state
    payload[20] = 0x87  # high

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("22:33:44:55:66:77", adv)
    assert parsed is not None

    # Core fields
    assert parsed.device_name == "BroodMinder-Scale W 55:66:77"
    assert parsed.model == 57
    assert parsed.battery_percent == 100
    assert parsed.humidity_percent == 55
    assert parsed.temperature_c is not None
    assert abs(parsed.temperature_c - 1.23) < 1e-6

    # Extended fields
    assert parsed.elapsed_s == 0x1234
    assert parsed.weight_l_kg is not None
    assert abs(parsed.weight_l_kg - 12.34) < 1e-6
    assert parsed.weight_r_kg is not None
    assert abs(parsed.weight_r_kg - 5.00) < 1e-6
    assert parsed.swarm_time_utc is None
    assert parsed.swarm_time_supported is False
    assert parsed.weight_realtime_total_kg is not None
    assert abs(parsed.weight_realtime_total_kg - 20.00) < 1e-6
    assert parsed.swarm_state_numeric is None

    # Verify entity export
    entities = extract_entities(parsed)
    assert entities[SENSOR_BATT] == 100
    assert entities[SENSOR_HUM] == 55
    assert math.isclose(entities[SENSOR_TEMP], 1.23, abs_tol=1e-6)
    assert entities[SENSOR_SAMPLE_COUNT] == 0x1234
    assert math.isclose(entities[SENSOR_WEIGHT_L], 12.34, abs_tol=1e-6)
    assert math.isclose(entities[SENSOR_WEIGHT_R], 5.00, abs_tol=1e-6)
    assert math.isclose(entities[SENSOR_WEIGHT_REALTIME], 20.00, abs_tol=1e-6)
    assert SENSOR_SWARM_STATE not in entities
    assert SENSOR_SWARM_TIME not in entities


def _t_payload_with_swarm_time(swarm_time_unix: int) -> bytes:
    payload = bytearray(21)  # we need up to index 20 inclusive
    payload[0] = 47  # model T
    payload[4] = 100  # battery %
    payload[15:19] = swarm_time_unix.to_bytes(4, "little")  # SM time, LSB first
    payload[19] = 29  # swarm state: swarm event detected
    return bytes(payload)


@pytest.mark.parametrize(
    ("swarm_time_unix", "expected"),
    [
        (1420070400, datetime.datetime(2015, 1, 1, tzinfo=datetime.UTC)),  # cutoff
        (1420070399, None),  # one second before the cutoff
        (0, None),  # no event recorded since boot
    ],
)
def test_GIVEN_swarm_time_around_2015_WHEN_parse_THEN_only_synced_time_is_reported(
    swarm_time_unix: int, expected: datetime.datetime | None
) -> None:
    """Verifies swarm times before 2015 are reported as None, but the entity key is kept."""

    adv = {MANUFACTURER_ID: _t_payload_with_swarm_time(swarm_time_unix)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None
    assert parsed.swarm_time_supported is True
    assert parsed.swarm_time_utc == expected

    entities = extract_entities(parsed)
    assert SENSOR_SWARM_TIME in entities
    assert entities[SENSOR_SWARM_TIME] == expected
