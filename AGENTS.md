# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project

A Home Assistant custom integration (domain `broodminder`) that passively reads
BroodMinder beehive sensors from Bluetooth LE advertisements. It's distributed via HACS.

- `custom_components/broodminder/` — the integration
  - `ble_parser.py` — decodes manufacturer data (ID `0x028D`) into `ManufacturerData`
  - `config_flow.py` — Bluetooth discovery flow, one config entry per device address, and the
    per-hive brood settings (options flow)
  - `sensor.py` — maps parsed data to sensor entities via HA's passive Bluetooth processor,
    plus the Brood and Likely brood break since sensors
  - `brood.py` — brood estimate and likely brood break algorithms, without Home Assistant
    dependencies
  - `brood_tracker.py` — per-hive sampling, outdoor temperature lookup, storage (versioned, with
    migrations) and repairs for the brood estimate and likely brood break
  - `const.py` — payload indices, model IDs, entity keys, brood estimate and brood break
    constants
  - `compat.py` — differences between the supported Home Assistant versions (see below)
  - `brand/` — the integration's icon (`icon.png` 256×256, `icon@2x.png` 512×512), which Home
    Assistant 2026.3+ serves from here; older versions only use home-assistant/brands
- `BROOD_ESTIMATE.md` — technical specification of the brood estimate and likely brood break
  (see below)
- `tests/` — pytest suite
- `scripts/` — developer scripts (see below)
- `requirements/` — development requirements per Home Assistant version (see below)
- `config/` — local Home Assistant config for `scripts/develop`, one directory per Home
  Assistant version; only the shared `configuration.yaml` is tracked

## Environment

Development happens in the devcontainer (`.devcontainer/devcontainer.json`). The integration
supports two ends of a range of Home Assistant versions, and everything is tested against both:

- **minimum** — the oldest supported version, the `homeassistant` version in `hacs.json`
  (2025.9), on Python 3.13. `requirements/minimum.txt` pins it; change it only together with
  `hacs.json`.
- **latest** — the newest version `pytest-homeassistant-custom-component` supports, on the Python
  version that one needs (3.14). `scripts/bump_latest.py` writes `requirements/latest.txt`;
  don't edit it by hand. A weekly workflow runs it and opens a pull request (see CI).

Both include `requirements/dev.txt`, the shared tools. Each plugin release is built against one
Home Assistant release (e.g. `0.13.281` ↔ `2025.9.4`), so the two always change together. The
first line of each file, `# python: ...`, is the Python version its environment is created
with.

```bash
scripts/setup [minimum|latest]   # create .venv-minimum and .venv-latest with uv (default: both)
```

VS Code uses `.venv-minimum`, so completions only offer what the oldest version has. Select
`.venv-latest` as interpreter to check against the newest one.

Code that must differ between the two versions goes in `compat.py`, with the version that
brought the newer behaviour, so it can be removed when the minimum moves past it.

## Building and running

There's no build step; the integration is plain Python loaded by Home Assistant.

```bash
scripts/develop [minimum|latest]  # run Home Assistant on http://localhost:8123 (default: minimum)
```

Each version has its own configuration directory, `config/minimum` and `config/latest`: a newer
Home Assistant migrates `.storage` to versions an older one can't read.

The devcontainer has no Bluetooth adapter, so `scripts/develop` only proves the integration
loads without errors. No devices will be discovered.

## Testing

```bash
scripts/test                                # full suite against both versions, with combined
                                            # coverage (htmlcov/, coverage.xml)
scripts/test latest tests/test_config_flow.py   # one module against one version
```

A test that only passes on one version is a failure: fix the code (in `compat.py` where the
versions differ), not the test. Home Assistant's warnings for deprecated calls
(`Detected that custom integration 'broodminder' ...`) in the latest run are fixed the same way.

- `tests/test_ble_parser.py`, `tests/test_sensor.py` and `tests/test_brood.py` are plain unit
  tests.
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

## CI

GitHub Actions run on pushes to `main` and `develop` and on pull requests:

- `.github/workflows/ci.yml` — `scripts/lint ci`, and pytest against minimum and latest.
- `.github/workflows/bump-latest.yml` — weekly (and manually): runs `scripts/bump_latest.py` on
  `develop` and, when the latest Home Assistant changed, opens a pull request and starts CI on
  it. GitHub only lets it open the pull request with "Allow GitHub Actions to create and approve
  pull requests" enabled in the repository settings; the schedule only runs once the workflow is
  on `main`.
- `.github/workflows/release.yml` — GitHub release on version tags (see Changelog).
- `.github/workflows/validate.yml` — hassfest and HACS validation (also weekly). Hassfest
  requires `manifest.json` keys as `domain`, `name`, then alphabetical.

Neither validator can run in the devcontainer, so check their results on GitHub.

## README

`README.md` is the user documentation shown on GitHub and in HACS. Update it in the same commit
as any change to what it describes: the sensors and what they mean, the sensors-per-device table,
supported devices, or installation and setup. Like the changelog, write it for beekeepers using
Home Assistant, not programmers.

## Brood estimate specification

`BROOD_ESTIMATE.md` is the technical specification of the brood estimate and the likely brood
break: requirements, design decisions, formulas, constants, settings, repairs, persistence, and
which tests verify which requirement. It's used for review and verification later, so it must
match the code.

- Update it in the same commit as any change to the brood estimate's behaviour: the algorithm
  or its constants, the outdoor temperature lookup, the settings, the Brood sensor and its
  attributes, the likely brood break and its sensor, the repairs, storage, or which models get a
  brood estimate.
- When the algorithm or a constant changes, recompute the reference values table (section
  6.8) with the scenarios in `tests/test_brood.py`, and the table of how they count for the
  likely brood break (section 7.6).
- Give new requirements and decisions the next free ID (`R32`, `D36`, ...) and don't renumber
  existing ones. When a decision is reversed, update it and record why.
- Every change to the format of the brood history file (`.storage/broodminder.brood.*`)
  increases `BROOD_STORAGE_VERSION`, adds a migration from the previous version with a test,
  and adds the version to the table in section 12.1. Don't use `minor_version` (D30).
- Keep the verification table (section 15) in step with the tests: add new tests and rename
  renamed ones.
- Unlike the README and changelog, write it for developers reviewing the code.

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): one section
per released version (matching the git tags) with its date, newest first, and a top section
for the next version marked `Unreleased`, numbered after `version` in `manifest.json`.

- Update it with every finished change that affects users, in the same commit.
- Write for beekeepers using Home Assistant, not programmers: describe what they see or can
  do, not the code (e.g. "Temperatures are shown with one decimal", not
  "set `suggested_display_precision`").
- Group entries under `Added`, `Changed`, `Fixed`, `Removed`, `Documentation` or `Internal`.
- Tests, CI, linting, refactoring and developer tooling don't get their own entries: keep them
  as one line under `Internal` saying they're internal fixes and cleanups.
- On a release, replace `Unreleased` with the date, update the compare links at the bottom
  (the unreleased one points at `develop`) and start a new `Unreleased` section.

HACS shows the GitHub release notes, not `CHANGELOG.md`, in Home Assistant's update dialog.
`.github/workflows/release.yml` publishes them: pushing a version tag (e.g. `0.4.0`) creates a
GitHub release whose notes are that version's changelog section, extracted by
`scripts/release_notes.py <version>`. It fails if the section is missing, empty or still
`Unreleased`, so date the section before tagging. To (re)publish the notes of an existing tag,
run the workflow manually with that tag; it then uses the changelog of the branch it runs
from. Only the highest version is marked as the latest release.

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
