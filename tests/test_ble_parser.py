"""Tests for broodminder/ble_parser.py."""

# ruff: noqa: PLR2004

import datetime
import math

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



def test_GIVEN_invalid_payload__WHEN_parse_THEN_returns_none() -> None:  # noqa: N802
    """Verifies an advertisement with invalid manufacturer id."""

    parsed = parse_manufacturer_data("AA", {MANUFACTURER_ID: b"\x00\x01"})
    assert parsed is None


def test_GIVEN_model_t_WHEN_parse_with_battery_above_hundred_THEN_reports_hundred_percent() -> (
    None
):
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


def test_GIVEN_model_t_WHEN_parse_with_battery_between_zero_and_hundred_THEN_reports_temperature() -> (
    None
):
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


def test_GIVEN_model_t_WHEN_parse_with_humidity_value_THEN_reports_no_humidity() -> None:  # noqa: N802
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


def test_GIVEN_model_t_WHEN_parse_with_temperature_value_THEN_reports_temperature() -> None:  # noqa: N802
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

    # approx 42.5 C
    assert parsed.temperature_c is not None
    assert math.isclose(parsed.temperature_c, 42.5, rel_tol=1e-3, abs_tol=1e-3)

    entities = extract_entities(parsed)
    assert SENSOR_TEMP in entities


def test_GIVEN_model_th_WHEN_parse_with_temperature_and_humidity_THEN_reports_temperature_and_humidity() -> (
    None
):
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
    assert parsed.model == 56
    assert parsed.humidity_percent == 55
    assert parsed.temperature_c is not None
    assert abs(parsed.temperature_c - 1.23) < 1e-6


def test_parse_primary_extended_fields_model_th() -> None:
    """Validate parsing of the additional PRIMARY fields and their exposure via extract_entities for model TH:
    - Elapsed seconds (bytes 15-16 overall → indices 5-6)
    - Weight L / Weight R (bytes 20-23 overall → indices 10-13)
    - Humidity (byte 24 → index 14)
    - SM time (bytes 25-28 → indices 15-18)
    - Realtime total weight (bytes 29-30 → indices 19-20)
    - Swarm state (byte 29 → index 19, raw).
    """  # noqa: D205
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
    assert parsed.swarm_time_utc == datetime.datetime(
        1970, 7, 14, 4, 20, 15, 0, tzinfo=datetime.UTC
    )

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
    assert entities[SENSOR_SWARM_TIME] == datetime.datetime(
        1970, 7, 14, 4, 20, 15, 0, tzinfo=datetime.UTC
    )


def test_parse_primary_extended_fields_model_w() -> None:
    """Validate parsing of the additional PRIMARY fields and their exposure via extract_entities for model w:
    - Elapsed seconds (bytes 15-16 overall → indices 5-6)
    - Weight L / Weight R (bytes 20-23 overall → indices 10-13)
    - Humidity (byte 24 → index 14)
    - SM time (bytes 25-28 → indices 15-18)
    - Realtime total weight (bytes 29-30 → indices 19-20)
    - Swarm state (byte 29 → index 19, raw).
    """  # noqa: D205
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
