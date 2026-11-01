"""Parser for BroodMinder BLE advertisement manufacturer data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .const import (
    CALCULATED_TOTAL_WEIGHT_MODELS,
    EXTRA_WEIGHT_MODELS,
    HALF_HIVE_WEIGHT_FACTOR,
    ID_TO_MODEL,
    IDX_BATTERY,
    IDX_ELAPSED_H,
    IDX_ELAPSED_L,
    IDX_HUMIDITY,
    IDX_MODEL,
    IDX_RT_TEMP1_L,
    IDX_RT_TEMP2_L,
    IDX_RT_TOTAL_H,
    IDX_RT_TOTAL_L_OR_SWARM_STATE,
    IDX_TEMP_H,
    IDX_TEMP_L,
    IDX_VER_MAJOR,
    IDX_VER_MINOR,
    IDX_WEIGHT_L_H,
    IDX_WEIGHT_L_L,
    IDX_WEIGHT_R_H,
    IDX_WEIGHT_R_L,
    IDX_WL2_SM0,
    IDX_WL2_SM1,
    IDX_WR2_SM2,
    IDX_WR2_SM3,
    MANUFACTURER,
    MANUFACTURER_ID,
    MIN_PAYLOAD_LEN,
    MODEL_T,
    MODEL_TH,
    NO_HUMIDITY_MODELS,
    REALTIME_MODELS,
    SCALE_MODELS,
    SENSOR_BATT,
    SENSOR_HUM,
    SENSOR_PERCENTAGE_MAXIMUM,
    SENSOR_PERCENTAGE_MINIMUM,
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
    SPECIAL_TEMP_MODELS_F,
    SWARM_TIME_MIN_VALID_UNIX,
    TEMP_RAW_INVALID,
    WEIGHT_RAW_NO_READING,
    WEIGHT_RAW_NOT_CONNECTED,
)


@dataclass(frozen=True)
class ManufacturerData:
    """High-level parsed advertisement values."""

    address: str
    model: int
    model_name: str
    firmware: str | None
    temperature_c: float | None
    humidity_percent: int | None
    battery_percent: int | None
    device_name: str
    device_id: str  # address or BroodMinder ID string

    # Extra parsed fields from PRIMARY (optional)
    elapsed_s: int | None = None
    temperature_rt_c: float | None = None
    weight_l_kg: float | None = None
    weight_r_kg: float | None = None
    weight_l2_kg: float | None = None
    weight_r2_kg: float | None = None
    weight_realtime_total_kg: float | None = None
    swarm_state_numeric: int | None = None
    swarm_time_utc: datetime | None = None  # None if the device clock wasn't synced
    swarm_time_supported: bool = False


def _u8(payload: bytes, idx: int) -> int | None:
    """Return the byte at idx, or None if the payload is too short."""
    return payload[idx] if len(payload) > idx else None


def _u16(payload: bytes, lo: int, hi: int) -> int | None:
    """Return the little-endian 16-bit value of bytes lo and hi, or None if too short."""
    if len(payload) <= max(lo, hi):
        return None
    return payload[lo] | (payload[hi] << 8)


def _u32(payload: bytes, start: int) -> int | None:
    """Return the little-endian 32-bit value of four bytes from start, or None if too short."""
    if len(payload) < start + 4:
        return None
    return int.from_bytes(payload[start : start + 4], "little")


def _parse_temperature_c(model: int, raw: int | None) -> float | None:
    if raw is None or raw == TEMP_RAW_INVALID:
        return None

    if model in SPECIAL_TEMP_MODELS_F:
        # raw is 16-bit → °C via SHT-like formula in docs
        return raw / (2**16) * 165 - 40

    # Others: centiC with +5000 offset
    return (raw - 5000) / 100.0


def _parse_battery(raw: int | None) -> int | None:
    # Clamp to HA's 0..100 expectation; some frames can exceed 100.
    if raw is None or raw < 0:
        return None

    return min(SENSOR_PERCENTAGE_MAXIMUM, max(SENSOR_PERCENTAGE_MINIMUM, raw))


def _parse_humidity(model: int, raw: int | None) -> int | None:
    if model in NO_HUMIDITY_MODELS or raw is None:
        return None

    if not (SENSOR_PERCENTAGE_MINIMUM <= raw <= SENSOR_PERCENTAGE_MAXIMUM):
        return None

    return raw


def _parse_weight_kg(model: int, raw: int | None, *, extra_channel: bool = False) -> float | None:
    if model not in SCALE_MODELS or raw is None:
        return None

    if raw == WEIGHT_RAW_NO_READING:
        return None
    if extra_channel and raw == WEIGHT_RAW_NOT_CONNECTED:
        return None

    # Signed with -32767 offset; then scale 1/100 (kg)
    return (raw - 32767) / 100.0


def _parse_swarm_time(model: int, raw: int | None) -> datetime | None:
    """Convert the 32-bit swarm time to a UTC datetime for T/TH models (per docs)."""
    if (model in MODEL_T or model in MODEL_TH) and raw is not None:
        if raw < SWARM_TIME_MIN_VALID_UNIX:
            return None
        try:
            return datetime.fromtimestamp(raw, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    return None


def _parse_swarm_state(model: int, raw: int | None) -> int | None:
    if model in MODEL_T or model in MODEL_TH:
        return raw

    return None


def _get_device_id_from_mac_address(mac_address: str) -> str:
    parts = mac_address.split(":")
    return ":".join(parts[-3:])


def _get_model_name_from_model_id(model_id: int) -> str:
    return ID_TO_MODEL.get(model_id, "Unknown")


def parse_manufacturer_data(address: str, mfg_data: dict[int, bytes]) -> ManufacturerData | None:
    """Parses the manufacturer data of the advertisement."""

    payload = mfg_data.get(MANUFACTURER_ID)
    # We need up to index 20 (inclusive) if present → len >= 21
    if (
        not payload or len(payload) < MIN_PAYLOAD_LEN
    ):  # keep permissive; we'll guard per-field reads
        return None

    model = payload[IDX_MODEL]
    model_name = _get_model_name_from_model_id(model)

    device_id = _get_device_id_from_mac_address(address)
    device_name = f"{MANUFACTURER}-{model_name} {device_id}"

    ver_minor = payload[IDX_VER_MINOR] if len(payload) > IDX_VER_MINOR else 0
    ver_major = payload[IDX_VER_MAJOR] if len(payload) > IDX_VER_MAJOR else 0
    fw = f"{ver_major}.{ver_minor}"

    battery = _parse_battery(_u8(payload, IDX_BATTERY))
    temp_c = _parse_temperature_c(model, _u16(payload, IDX_TEMP_L, IDX_TEMP_H))
    humidity = _parse_humidity(model, _u8(payload, IDX_HUMIDITY))
    elapsed_s = _u16(payload, IDX_ELAPSED_L, IDX_ELAPSED_H)

    # Realtime temperature (LSB and MSB are not adjacent)
    temperature_rt_c = None
    if model in REALTIME_MODELS:
        temperature_rt_c = _parse_temperature_c(
            model, _u16(payload, IDX_RT_TEMP1_L, IDX_RT_TEMP2_L)
        )

    weight_l_kg = _parse_weight_kg(model, _u16(payload, IDX_WEIGHT_L_L, IDX_WEIGHT_L_H))
    weight_r_kg = _parse_weight_kg(model, _u16(payload, IDX_WEIGHT_R_L, IDX_WEIGHT_R_H))

    # Extra weight channels share their bytes with the swarm time below
    weight_l2_kg = None
    weight_r2_kg = None
    if model in EXTRA_WEIGHT_MODELS:
        weight_l2_kg = _parse_weight_kg(
            model, _u16(payload, IDX_WL2_SM0, IDX_WL2_SM1), extra_channel=True
        )
        weight_r2_kg = _parse_weight_kg(
            model, _u16(payload, IDX_WR2_SM2, IDX_WR2_SM3), extra_channel=True
        )

    # Realtime total shares its low byte with the swarm state below
    weight_realtime_total_kg = None
    if model in REALTIME_MODELS:
        weight_realtime_total_kg = _parse_weight_kg(
            model, _u16(payload, IDX_RT_TOTAL_L_OR_SWARM_STATE, IDX_RT_TOTAL_H)
        )

    # Models without a realtime total: calculate it from the left and right weights
    if (
        model in CALCULATED_TOTAL_WEIGHT_MODELS
        and weight_l_kg is not None
        and weight_r_kg is not None
    ):
        weight_realtime_total_kg = round(HALF_HIVE_WEIGHT_FACTOR * (weight_l_kg + weight_r_kg), 2)

    # SwarmMinder (T/TH models): swarm time and state, in the extra and realtime weight bytes
    swarm_time_raw = _u32(payload, IDX_WL2_SM0)
    swarm_time_supported = swarm_time_raw is not None and (model in MODEL_T or model in MODEL_TH)
    swarm_time_dt = _parse_swarm_time(model, swarm_time_raw)
    swarm_state = _parse_swarm_state(model, _u8(payload, IDX_RT_TOTAL_L_OR_SWARM_STATE))

    return ManufacturerData(
        address=address,
        model=model,
        model_name=model_name,
        firmware=fw,
        temperature_c=temp_c,
        humidity_percent=humidity,
        battery_percent=battery,
        device_name=device_name,
        device_id=address,
        elapsed_s=elapsed_s,
        temperature_rt_c=temperature_rt_c,
        weight_l_kg=weight_l_kg,
        weight_r_kg=weight_r_kg,
        weight_l2_kg=weight_l2_kg,
        weight_r2_kg=weight_r2_kg,
        weight_realtime_total_kg=weight_realtime_total_kg,
        swarm_state_numeric=swarm_state,
        swarm_time_utc=swarm_time_dt,
        swarm_time_supported=swarm_time_supported,
    )


def extract_entities(parsed: ManufacturerData) -> dict[str, Any]:
    """Return a key->value map for entities."""

    data: dict[str, Any] = {}
    if parsed.temperature_c is not None:
        data[SENSOR_TEMP] = parsed.temperature_c
    if parsed.temperature_rt_c is not None:
        data[SENSOR_TEMP_RT] = parsed.temperature_rt_c
    if parsed.humidity_percent is not None:
        data[SENSOR_HUM] = parsed.humidity_percent
    if parsed.battery_percent is not None:
        data[SENSOR_BATT] = parsed.battery_percent
    if parsed.elapsed_s is not None:
        data[SENSOR_SAMPLE_COUNT] = parsed.elapsed_s
    if parsed.weight_l_kg is not None:
        data[SENSOR_WEIGHT_L] = parsed.weight_l_kg
    if parsed.weight_r_kg is not None:
        data[SENSOR_WEIGHT_R] = parsed.weight_r_kg
    if parsed.weight_l2_kg is not None:
        data[SENSOR_WEIGHT_L2] = parsed.weight_l2_kg
    if parsed.weight_r2_kg is not None:
        data[SENSOR_WEIGHT_R2] = parsed.weight_r2_kg
    if parsed.weight_realtime_total_kg is not None:
        data[SENSOR_WEIGHT_REALTIME] = parsed.weight_realtime_total_kg
    if parsed.swarm_state_numeric is not None:
        data[SENSOR_SWARM_STATE] = parsed.swarm_state_numeric
    if parsed.swarm_time_supported:
        # Keep None so the entity shows unknown instead of a stale or missing value
        data[SENSOR_SWARM_TIME] = parsed.swarm_time_utc
    return data
