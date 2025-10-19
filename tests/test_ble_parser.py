"""Tests for broodminder/ble_parser.py."""

import math

from custom_components.broodminder.ble_parser import extract_entities, parse_manufacturer_data
from custom_components.broodminder.const import (
    MANUFACTURER_ID,
    SENSOR_BATT,
    SENSOR_HUM,
    SENSOR_TEMP,
)


def test_parse_special_temp_model_no_humidity() -> None:
    # Model 41 uses the special 16-bit scale; humidity not present for this model
    # payload indices: 0:model, 1:ver minor, 2:ver major, 4:battery, 7-8:temp, 14:humidity
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
    assert parsed.battery_percent == 88
    assert parsed.humidity_percent is None  # filtered out by model rules
    # approx 42.5 C
    assert parsed.temperature_c is not None
    assert math.isclose(parsed.temperature_c, 42.5, rel_tol=1e-3, abs_tol=1e-3)

    entities = extract_entities(parsed)
    assert SENSOR_TEMP in entities and SENSOR_BATT in entities and SENSOR_HUM not in entities


def test_parse_default_temp_and_humidity() -> None:
    # Model 60 uses default centi-C with +5000 offset
    # raw = 0x1403 = 5123 -> (5123 - 5000)/100 = 1.23 C
    payload = bytearray(15)
    payload[0] = 60  # model
    payload[1] = 2
    payload[2] = 1
    payload[4] = 100  # battery %
    payload[7] = 0x03
    payload[8] = 0x14
    payload[14] = 55  # 55% RH

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("11:22:33:44:55:66", adv)
    assert parsed is not None
    assert parsed.model == 60
    assert parsed.battery_percent == 100
    assert parsed.humidity_percent == 55
    assert parsed.temperature_c is not None
    assert abs(parsed.temperature_c - 1.23) < 1e-6


def test_invalid_payload_returns_none() -> None:
    parsed = parse_manufacturer_data("AA", {MANUFACTURER_ID: b"\x00\x01"})
    assert parsed is None
