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
    SENSOR_SWARM_STATE,
    SENSOR_SWARM_TIME,
    SENSOR_TEMP,
    SENSOR_TEMP_RT,
    SENSOR_WEIGHT_L,
    SENSOR_WEIGHT_L2,
    SENSOR_WEIGHT_R,
    SENSOR_WEIGHT_R2,
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


def test_GIVEN_t_41_WHEN_parse_THEN_reports_temperature() -> None:
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


def test_GIVEN_th_56_WHEN_parse_THEN_reports_temp_and_humidity() -> None:
    """Verifies an advertisement with temperature and humidity."""

    # Model 56 uses default centi-C with +5000 offset
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


def test_GIVEN_th_56_WHEN_parse_THEN_reports_extended_fields() -> None:
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


def test_GIVEN_scale_w_57_WHEN_parse_THEN_reports_extended_fields() -> None:
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


def _scale_w_43_doc_payload() -> bytearray:
    """Model 43 advertisement from the BroodMinder docs (87_physics_and_tech_stuff)."""
    payload = bytearray(21)
    payload[0] = 0x2B  # model 43
    payload[1] = 0x15  # v.minor
    payload[2] = 0x02  # v.major
    payload[3] = 0x00  # realtime temperature LSB: not sent by model 43
    payload[4] = 0x02  # battery %
    payload[5] = 0x21  # elapsed LSB: 33
    payload[6] = 0x00  # elapsed MSB
    payload[7] = 0xD0  # temperature LSB: SHT raw 0x62D0 -> 23.69 °C
    payload[8] = 0x62  # temperature MSB
    payload[9] = 0x00  # realtime temperature MSB: not sent by model 43
    payload[10] = 0xFF  # weight left LSB: 0x7FFF -> 0.00 kg
    payload[11] = 0x7F  # weight left MSB
    payload[12] = 0x05  # weight right LSB: 0x8005 -> 0.06 kg
    payload[13] = 0x80  # weight right MSB
    payload[14] = 0x37  # humidity: 55%
    payload[15] = 0x07  # device id 43:30:07, LSB first: not a weight
    payload[16] = 0x30  # device id
    payload[17] = 0x43  # device id
    payload[18] = 0x00  # unused
    payload[19] = 0x00  # realtime total LSB: not sent by model 43
    payload[20] = 0x00  # realtime total MSB
    return payload


def test_GIVEN_scale_w_43_doc_advertisement_WHEN_parse_THEN_reports_only_sent_values() -> None:
    """Verifies model 43 shows its weights and a calculated total, without realtime fields."""

    adv = {MANUFACTURER_ID: bytes(_scale_w_43_doc_payload())}
    parsed = parse_manufacturer_data("AA:BB:CC:43:30:07", adv)
    assert parsed is not None
    assert parsed.model_name == "Scale W"
    assert parsed.firmware == "2.21"

    entities = extract_entities(parsed)
    assert set(entities) == {
        SENSOR_BATT,
        SENSOR_HUM,
        SENSOR_SAMPLE_COUNT,
        SENSOR_TEMP,
        SENSOR_WEIGHT_L,
        SENSOR_WEIGHT_R,
        SENSOR_WEIGHT_REALTIME,
    }
    assert entities[SENSOR_BATT] == 2
    assert entities[SENSOR_HUM] == 55
    assert entities[SENSOR_SAMPLE_COUNT] == 33
    assert math.isclose(entities[SENSOR_TEMP], 23.69, abs_tol=0.01)
    assert entities[SENSOR_WEIGHT_L] == 0.0
    assert entities[SENSOR_WEIGHT_R] == 0.06
    assert entities[SENSOR_WEIGHT_REALTIME] == 0.12  # 2 x (left + right)


def test_GIVEN_scale_w_43_WHEN_one_side_has_no_reading_THEN_no_total_weight() -> None:
    """Verifies the calculated total is left out when one side of the scale has no weight."""

    payload = _scale_w_43_doc_payload()
    payload[12] = 0xFF  # weight right LSB: 0xFFFF -> no reading
    payload[13] = 0xFF  # weight right MSB

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:43:30:07", adv)
    assert parsed is not None

    entities = extract_entities(parsed)
    assert entities[SENSOR_WEIGHT_L] == 0.0
    assert SENSOR_WEIGHT_R not in entities
    assert SENSOR_WEIGHT_REALTIME not in entities


@pytest.mark.parametrize(
    ("model", "has_realtime"),
    [
        (41, False),  # T
        (47, True),  # T
        (42, False),  # TH
        (56, True),  # TH
        (43, False),  # Scale W
        (57, True),  # Scale W
        (49, True),  # Scale W3/W4
        (58, True),  # DIY
        (52, False),  # SubHub
        (54, False),  # Hub 4G
        (60, False),  # Hub Wifi
        (63, False),  # BeeDar
        (99, False),  # unknown
    ],
)
def test_GIVEN_model_WHEN_parse_THEN_realtime_temperature_only_for_documented_models(
    model: int, has_realtime: bool
) -> None:
    """Verifies only models documented to send it report a realtime temperature."""

    payload = bytearray(21)
    payload[0] = model  # model
    payload[3] = 0x4C  # realtime temperature LSB: 7500 -> 25.00 °C
    payload[4] = 80  # battery %
    payload[9] = 0x1D  # realtime temperature MSB

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None

    entities = extract_entities(parsed)
    if has_realtime:
        assert entities[SENSOR_TEMP_RT] == 25.0
    else:
        assert SENSOR_TEMP_RT not in entities


@pytest.mark.parametrize(
    ("raw", "expected_main", "expected_extra"),
    [
        (0x7FFF, 0.0, None),  # empty scale on a main channel, no load cell on an extra one
        (0x8005, 0.06, 0.06),
        (0xFFFF, None, None),  # no reading
    ],
)
def test_GIVEN_raw_weight_WHEN_parse_THEN_main_and_extra_channels_decode_it(
    raw: int, expected_main: float | None, expected_extra: float | None
) -> None:
    """Verifies which raw weight values are a weight on the main and extra channels."""

    payload = bytearray(21)
    payload[0] = 57  # model: Scale W with extra channels
    payload[4] = 80  # battery %
    payload[10] = raw & 0xFF  # weight left LSB
    payload[11] = raw >> 8  # weight left MSB
    payload[12] = raw & 0xFF  # weight right LSB
    payload[13] = raw >> 8  # weight right MSB
    payload[15] = raw & 0xFF  # weight left 2 LSB
    payload[16] = raw >> 8  # weight left 2 MSB
    payload[17] = raw & 0xFF  # weight right 2 LSB
    payload[18] = raw >> 8  # weight right 2 MSB

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None
    assert parsed.weight_l_kg == expected_main
    assert parsed.weight_r_kg == expected_main
    assert parsed.weight_l2_kg == expected_extra
    assert parsed.weight_r2_kg == expected_extra


@pytest.mark.parametrize(
    ("model", "model_name", "has_humidity"),
    [
        (49, "Scale W3/W4", False),
        (57, "Scale W", True),
        (58, "DIY", True),
    ],
)
def test_GIVEN_scale_with_extra_channels_WHEN_parse_THEN_reports_all_weights(
    model: int, model_name: str, has_humidity: bool
) -> None:
    """Verifies scales with extra channels report all four weights and the realtime total."""

    payload = bytearray(21)
    payload[0] = model  # model
    payload[1] = 2  # v.minor
    payload[2] = 1  # v.major
    payload[3] = 0x4C  # realtime temperature LSB: 7500 -> 25.00 °C
    payload[4] = 75  # battery %
    payload[5] = 0x34  # elapsed LSB: 0x1234
    payload[6] = 0x12  # elapsed MSB
    payload[7] = 0x03  # temperature LSB: 5123 -> 1.23 °C
    payload[8] = 0x14  # temperature MSB
    payload[9] = 0x1D  # realtime temperature MSB
    payload[10] = 0xE7  # weight left LSB: 10.00 kg -> 32767 + 1000 = 0x83E7
    payload[11] = 0x83  # weight left MSB
    payload[12] = 0x19  # weight right LSB: 10.50 kg -> 32767 + 1050 = 0x8419
    payload[13] = 0x84  # weight right MSB
    payload[14] = 50  # humidity %, ignored by model 49
    payload[15] = 0xB5  # weight left 2 LSB: 9.50 kg -> 32767 + 950 = 0x83B5
    payload[16] = 0x83  # weight left 2 MSB
    payload[17] = 0xCE  # weight right 2 LSB: 9.75 kg -> 32767 + 975 = 0x83CE
    payload[18] = 0x83  # weight right 2 MSB
    payload[19] = 0x86  # realtime total LSB: 39.75 kg -> 32767 + 3975 = 0x8F86
    payload[20] = 0x8F  # realtime total MSB

    adv = {MANUFACTURER_ID: bytes(payload)}
    parsed = parse_manufacturer_data("AA:BB:CC:DD:EE:FF", adv)
    assert parsed is not None
    assert parsed.model_name == model_name

    entities = extract_entities(parsed)
    assert set(entities) - {SENSOR_HUM} == {
        SENSOR_BATT,
        SENSOR_SAMPLE_COUNT,
        SENSOR_TEMP,
        SENSOR_TEMP_RT,
        SENSOR_WEIGHT_L,
        SENSOR_WEIGHT_R,
        SENSOR_WEIGHT_L2,
        SENSOR_WEIGHT_R2,
        SENSOR_WEIGHT_REALTIME,
    }
    assert (SENSOR_HUM in entities) is has_humidity
    assert entities[SENSOR_TEMP_RT] == 25.0
    assert entities[SENSOR_WEIGHT_L] == 10.0
    assert entities[SENSOR_WEIGHT_R] == 10.5
    assert entities[SENSOR_WEIGHT_L2] == 9.5
    assert entities[SENSOR_WEIGHT_R2] == 9.75
    assert entities[SENSOR_WEIGHT_REALTIME] == 39.75
