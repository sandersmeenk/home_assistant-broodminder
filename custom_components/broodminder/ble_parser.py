from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import (
    IDX_BATTERY,
    IDX_HUMIDITY,
    IDX_MODEL,
    IDX_TEMP_H,
    IDX_TEMP_L,
    MANUFACTURER,
    MANUFACTURER_ID,
    NO_HUMIDITY_MODELS,
    SENSOR_BATT,
    SENSOR_HUM,
    SENSOR_TEMP,
    SPECIAL_TEMP_MODELS_F,
)


@dataclass(frozen=True)
class ParsedAdv:
    """High-level parsed advertisement values."""

    address: str
    model: int
    firmware: str | None
    temperature_c: float | None
    humidity_percent: int | None
    battery_percent: int | None
    device_name: str
    device_id: str  # address or BroodMinder ID string


def _parse_temperature_c(model: int, lo: int, hi: int) -> float | None:
    raw = lo | (hi << 8)
    if raw == 0xFFFF:  # sometimes weight fields use 0x7FFF/0x8005; treat 0xFFFF as invalid temp
        return None
    if model in SPECIAL_TEMP_MODELS_F:
        # From BroodMinder doc: for models 41/42/43, raw is 16-bit where:
        # T[F] = (raw/2^16 * 165 - 40) * 9/5 + 32 ; convert to C at the end
        t_f = ((raw / (2**16)) * 165 - 40) * 9 / 5 + 32
        return (t_f - 32) * 5 / 9
    # Else: centiC with +5000 offset (i.e., 0.01 C units)
    # T[C] = (raw - 5000) / 100
    return (raw - 5000) / 100.0


def parse_manufacturer_data(address: str, mfg_data: dict[int, bytes]) -> ParsedAdv | None:
    payload = mfg_data.get(MANUFACTURER_ID)
    if not payload or len(payload) < 15:  # need up to humidity byte
        return None

    model = payload[IDX_MODEL]
    ver_minor = payload[1]
    ver_major = payload[2]
    fw = f"{ver_major}.{ver_minor}"

    batt = payload[IDX_BATTERY]
    battery = batt if 0 <= batt <= 100 else None

    temp_c = _parse_temperature_c(model, payload[IDX_TEMP_L], payload[IDX_TEMP_H])

    humidity = None
    if model not in NO_HUMIDITY_MODELS and len(payload) > IDX_HUMIDITY:
        h = payload[IDX_HUMIDITY]
        # Per docs, some models will send 0 here; keep 0 if model supports humidity
        humidity = h if 0 <= h <= 100 else None

    # Device label: "BroodMinder <model>" (we don't always get extended adv name)
    device_name = f"{MANUFACTURER} {model}"
    device_id = address

    return ParsedAdv(
        address=address,
        model=model,
        firmware=fw,
        temperature_c=temp_c,
        humidity_percent=humidity,
        battery_percent=battery,
        device_name=device_name,
        device_id=device_id,
    )


def extract_entities(parsed: ParsedAdv) -> dict[str, Any]:
    """Return a key->value map for entities."""
    data: dict[str, Any] = {}
    if parsed.temperature_c is not None:
        data[SENSOR_TEMP] = parsed.temperature_c
    if parsed.humidity_percent is not None:
        data[SENSOR_HUM] = parsed.humidity_percent
    if parsed.battery_percent is not None:
        data[SENSOR_BATT] = parsed.battery_percent
    return data
