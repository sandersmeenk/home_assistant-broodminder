from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .const import (
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
    MODEL_T,
    MODEL_TH,
    MODEL_W,
    MODEL_W3_W4,
    NO_HUMIDITY_MODELS,
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
)


@dataclass(frozen=True)
class ManufacturerData:
    """High-level parsed advertisement values."""

    address: str
    model: int
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
    swarm_time_utc: datetime | None = None


def _parse_temperature_c(model: int, lo: int, hi: int) -> float | None:
    raw = lo | (hi << 8)
    if raw in (0xFFFF,):  # invalid
        return None

    if model in SPECIAL_TEMP_MODELS_F:
        # raw is 16-bit → °C via SHT-like formula in docs (converted via °F path)
        t_f = ((raw / (2**16)) * 165 - 40) * 9 / 5 + 32
        return (t_f - 32) * 5 / 9

    # Others: centiC with +5000 offset
    return (raw - 5000) / 100.0


def _parse_battery(raw: int) -> int | None:
    battery = raw

    if not (SENSOR_PERCENTAGE_MINIMUM <= battery <= SENSOR_PERCENTAGE_MAXIMUM):
        battery = None

    return battery


def _parse_humidity(model: int, raw: int) -> int | None:
    humidity = None

    if model not in NO_HUMIDITY_MODELS:
        humidity = raw

        if not (SENSOR_PERCENTAGE_MINIMUM <= humidity <= SENSOR_PERCENTAGE_MAXIMUM):
            humidity = None

    return humidity


def _parse_weight_kg(model: int, lo: int, hi: int) -> float | None:
    weight = None

    if model in MODEL_W or model in MODEL_W3_W4:
        raw = lo | (hi << 8)

        # Known sentinel "no weight" values (docs/examples):
        if raw not in (0x7FFF, 0x8005, 0xFFFF):
            # Signed with -32767 offset; then scale 1/100 (kg)
            weight = (raw - 32767) / 100.0

    return weight



def _parse_swarm_time(model: int, t1: int, t2: int, t3: int, t4: int) -> datetime | None:
    """Convert four bytes to a UTC datetime for T/TH models (per docs)."""
    if model in MODEL_T or model in MODEL_TH:
        swarm_time_unix = t1 | (t2 << 8) | (t3 << 16) | (t4 << 24)
        try:
            return datetime.fromtimestamp(swarm_time_unix, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    return None


def _parse_swarm_state(model: int, ss: int) -> int | None:
    if model in MODEL_T or model in MODEL_TH:
        return ss

    return None


def parse_manufacturer_data(address: str, mfg_data: dict[int, bytes]) -> ManufacturerData | None:
    """Parses the manufacturer data of the advertisement."""

    payload = mfg_data.get(MANUFACTURER_ID)
    # We need up to index 20 (inclusive) if present → len >= 21
    if not payload or len(payload) < 5:  # keep permissive; we'll guard per-field reads
        return None

    model = payload[IDX_MODEL]
    ver_minor = payload[IDX_VER_MINOR] if len(payload) > IDX_VER_MINOR else 0
    ver_major = payload[IDX_VER_MAJOR] if len(payload) > IDX_VER_MAJOR else 0
    fw = f"{ver_major}.{ver_minor}"

    # Battery
    battery = None
    if len(payload) > IDX_BATTERY:
        battery = _parse_battery(payload[IDX_BATTERY])

    # Main temperature
    temp_c = None
    if len(payload) > IDX_TEMP_H:
        temp_c = _parse_temperature_c(model, payload[IDX_TEMP_L], payload[IDX_TEMP_H])

    # Humidity
    humidity = None
    if len(payload) > IDX_HUMIDITY:
        humidity = _parse_humidity(model, payload[IDX_HUMIDITY])

    # Elapsed seconds
    elapsed_s = None
    if len(payload) > IDX_ELAPSED_H:
        elapsed_s = payload[IDX_ELAPSED_L] | (payload[IDX_ELAPSED_H] << 8)

    # Realtime temperature
    temperature_rt_c = None
    if len(payload) > IDX_RT_TEMP1_L and len(payload) > IDX_RT_TEMP2_L:
        temperature_rt_c = _parse_temperature_c(model,
                                                payload[IDX_RT_TEMP1_L],
                                                payload[IDX_RT_TEMP2_L])

    # Weights
    weight_l_kg = None
    weight_r_kg = None
    if len(payload) > IDX_WEIGHT_R_H:
        weight_l_kg = _parse_weight_kg(model, payload[IDX_WEIGHT_L_L], payload[IDX_WEIGHT_L_H])
        weight_r_kg = _parse_weight_kg(model, payload[IDX_WEIGHT_R_L], payload[IDX_WEIGHT_R_H])

    # Extra channels or SM time
    weight_l2_kg = None
    weight_r2_kg = None
    swarm_time_dt = None

    if len(payload) > IDX_WR2_SM3:
        # Expose as swarm time for models where these are swarm time
        swarm_time_dt = _parse_swarm_time(
            model,
            payload[IDX_WL2_SM0],
            payload[IDX_WL2_SM1],
            payload[IDX_WR2_SM2],
            payload[IDX_WR2_SM3],
        )

        # Expose as weights for models where these are extra weight channels
        weight_l2_kg = _parse_weight_kg(model, payload[IDX_WL2_SM0], payload[IDX_WL2_SM1])
        weight_r2_kg = _parse_weight_kg(model, payload[IDX_WR2_SM2], payload[IDX_WR2_SM3])

    # Realtime total or swarm state
    weight_realtime_total_kg = None
    swarm_state = None

    if len(payload) > IDX_RT_TOTAL_H:
        swarm_state = _parse_swarm_state(model, payload[IDX_RT_TOTAL_L_OR_SWARM_STATE])
        weight_realtime_total_kg = _parse_weight_kg(
            model, payload[IDX_RT_TOTAL_L_OR_SWARM_STATE], payload[IDX_RT_TOTAL_H]
        )

    # Device label
    device_name = f"{MANUFACTURER} {model}"
    device_id = address

    return ManufacturerData(
        address=address,
        model=model,
        firmware=fw,
        temperature_c=temp_c,
        humidity_percent=humidity,
        battery_percent=battery,
        device_name=device_name,
        device_id=device_id,
        elapsed_s=elapsed_s,
        temperature_rt_c=temperature_rt_c,
        weight_l_kg=weight_l_kg,
        weight_r_kg=weight_r_kg,
        weight_l2_kg=weight_l2_kg,
        weight_r2_kg=weight_r2_kg,
        weight_realtime_total_kg=weight_realtime_total_kg,
        swarm_state_numeric=swarm_state,
        swarm_time_utc=swarm_time_dt,
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
    if parsed.swarm_time_utc is not None:
        data[SENSOR_SWARM_TIME] = parsed.swarm_time_utc
    return data
