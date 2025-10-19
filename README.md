# BroodMinder for Home Assistant

A zero-pairing, **advertisement-only** integration for BroodMinder devices. It listens for BLE manufacturer data (company ID `0x028D`) and exposes:

- Temperature (°C)
- Humidity (%RH) — where available
- Battery (%)

It uses Home Assistant’s shared Bluetooth scanner (Bleak) and the PassiveBluetooth* processor pattern for efficient, multi-proxy setups.

# Installation and setup

This integration is available in HACS (Home Assistant Community Store).

Just click the badge below:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sandersmeenk&repository=home_assistant-broodminder)

## How it works

- Matches advertisements by manufacturer ID `0x028D (653)` with `connectable: false`.
- Parses the payload described in BroodMinder’s doc:
  - Byte 0: model
  - Byte 4: battery (0–100)
  - Bytes 7–8: temperature (either special 16-bit scaling for models 41/42/43 or centi-C with +5000 offset for others)
  - Byte 14: humidity (`0` for models that don’t support humidity)
  Sources: HA Bluetooth docs; BroodMinder BLE Advertising Information.

## Supported devices

Any BroodMinder model that broadcasts temperature/humidity/battery in the standard manufacturer payload. Humidity is **not** present for models `{41, 47, 49, 52}` as per docs.

## Development notes

- Parse logic lives in `ble_parser.py` — unit tested in `tests/test_ble_parser.py`.
- Sensors/entities follow the passive Bluetooth processor pattern.

### Run tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
pytest -q
