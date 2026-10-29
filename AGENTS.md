# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project

A Home Assistant custom integration (domain `broodminder`) that passively reads
BroodMinder beehive sensors from Bluetooth LE advertisements. It's distributed via HACS.

- `custom_components/broodminder/` — the integration
  - `ble_parser.py` — decodes manufacturer data (ID `0x028D`) into `ManufacturerData`
  - `config_flow.py` — Bluetooth discovery flow, one config entry per device address
  - `sensor.py` — maps parsed data to sensor entities via HA's passive Bluetooth processor
  - `const.py` — payload indices, model IDs and entity keys
- `tests/` — pytest suite
- `scripts/` — developer scripts (see below)
- `config/` — local Home Assistant config for `scripts/develop`; only
  `configuration.yaml` is tracked

## Environment

Development happens in the devcontainer (`.devcontainer/devcontainer.json`, Python 3.13).

```bash
scripts/setup    # install requirements.txt and requirements_test.txt
```

The `homeassistant` version in `requirements.txt` and `pytest-homeassistant-custom-component`
in `requirements_test.txt` must match: each plugin release is built against one
Home Assistant release (e.g. `0.13.281` ↔ `2025.9.4`). Bump them together.

## Building and running

There's no build step; the integration is plain Python loaded by Home Assistant.

```bash
scripts/develop  # run a local Home Assistant on http://localhost:8123 with this integration
```

The devcontainer has no Bluetooth adapter, so `scripts/develop` only proves the integration
loads without errors. No devices will be discovered.

## Testing

```bash
scripts/test                          # full suite with coverage (htmlcov/, coverage.xml)
pytest tests/test_config_flow.py      # a single module
```

- `tests/test_ble_parser.py` and `tests/test_sensor.py` are plain unit tests.
- `tests/test_config_flow.py` is an end-to-end test: it starts an in-memory Home Assistant,
  mocks a Bluetooth adapter, injects fake BroodMinder advertisements and checks discovery,
  config entries, devices and sensor states. Use this pattern for behaviour that spans
  discovery → entities.
- Test names follow `test_GIVEN_<state>_WHEN_<action>_THEN_<result>` with a one-line docstring.
- Build payloads byte by byte with a comment per index, as the existing tests do.
- Add or update tests with every behaviour change, and keep the suite passing.

## Code analysis

```bash
scripts/lint       # ruff format + ruff check --fix
scripts/lint ci    # report only, no changes
```

- Ruff config is in `.ruff.toml`: all rules enabled, with Home Assistant core's ignore list,
  98-character lines and Google-style docstrings.
- Don't add `noqa` or new ignores to silence a finding when the code can be fixed instead.
  Per-file `# ruff: noqa: PLR2004` is accepted in tests for magic numbers.
- `scripts/check_requirements.py` checks `manifest.json` requirements against Home Assistant's
  package constraints (`--current-ha-dev`, `--minimum-ha-version`). It needs network access.

Before finishing a change, run `scripts/lint` and `scripts/test`, and make sure both are clean.

## Home Assistant hosts: hands off

**Never access a real Home Assistant host for testing unless the user explicitly instructs you
to.** That includes `homeassistant.local` and any other address, over SSH, the REST or
WebSocket API, or Samba.

- Don't run `scripts/deploy` (`push`, `revert`, `backup` or `status`) on your own initiative.
  `push` and `revert` overwrite the installed integration and restart the user's production
  Home Assistant.
- An instruction covers only the action it names. Permission to run `status` isn't permission
  to `push`, and permission given once doesn't carry over to later tasks.
- Do all verification locally: the pytest suite, and `scripts/develop` in the devcontainer.
- If a change can only be verified on real hardware, say so and leave deploying to the user.
