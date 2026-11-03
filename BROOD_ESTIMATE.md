# Brood estimate: specification

Technical specification of the brood estimate in the BroodMinder integration: requirements,
design decisions, the algorithm with its formulas and constants, configuration, persistence and
how to verify it. It describes the implementation as of version 0.5.0.

- Status: implemented, constants not yet calibrated against real hives (see
  [Calibration](#13-calibration))
- Code: [`brood.py`](custom_components/broodminder/brood.py) (algorithm),
  [`brood_tracker.py`](custom_components/broodminder/brood_tracker.py) (sampling, outdoor
  temperature, storage, repairs), [`config_flow.py`](custom_components/broodminder/config_flow.py)
  (settings), [`sensor.py`](custom_components/broodminder/sensor.py) (entity),
  [`const.py`](custom_components/broodminder/const.py) (constants)
- Tests: [`tests/test_brood.py`](tests/test_brood.py),
  [`tests/test_config_flow.py`](tests/test_config_flow.py)

## Contents

1. [Purpose](#1-purpose)
2. [Background](#2-background)
3. [Requirements](#3-requirements)
4. [Design decisions](#4-design-decisions)
5. [Data collection](#5-data-collection)
6. [Algorithm](#6-algorithm)
7. [Outdoor temperature](#7-outdoor-temperature)
8. [Configuration](#8-configuration)
9. [Brood sensor entity](#9-brood-sensor-entity)
10. [Repairs and logging](#10-repairs-and-logging)
11. [Persistence and resource use](#11-persistence-and-resource-use)
12. [Lifecycle](#12-lifecycle)
13. [Calibration](#13-calibration)
14. [Verification](#14-verification)
15. [Known limitations](#15-known-limitations)
16. [References](#16-references)

## 1. Purpose

BroodMinder's Bees app and MyBroodMinder show a daily *brood level*: a percentage where 0% means
no brood and 100% a hive full of brood. BroodMinder computes it in its cloud and doesn't publish
the method. This integration provides a comparable estimate locally, inside Home Assistant, from
data it already has: the in-hive temperature that BroodMinder-T and -TH sensors broadcast over
Bluetooth, and an outdoor temperature from Home Assistant.

Out of scope: weight (scales), humidity, colony strength (number of bees), frames of brood as an
absolute number, and any cloud service.

## 2. Background

### 2.1 Why temperature indicates brood

Brood only develops within a narrow temperature range, 32 to 36 °C, optimally about 35 °C. A
colony with brood actively keeps the brood nest at that temperature, whatever the weather, by
heating and cooling. Without brood the colony has little reason to regulate, and the hive
temperature follows the outdoor temperature, a few degrees warmer from the colony's heat.

BroodMinder uses the same principle: a stable 35 °C is its *Optimal Brood Zone* and 100%; a hive
following the outdoor temperature is near 0%. It notes that the percentage is relative (compare
hives and days), depends on hive type, insulation and sensor placement, and is less accurate
below 20%, because the sensor measures one point and the brood can be far from it.

### 2.2 Findings from research

| Source | Finding used here |
|---|---|
| Godeau et al. (INRAE) | With the sensor *inside* the brood nest, the mean temperature was 34.4 to 35 °C regardless of how much brood there was. Temperature can't tell brood size from inside the brood nest; it tells whether the brood nest reaches the sensor. Weather (outdoor temperature) affected both level and stability. |
| Meikle et al. 2015 | The daily temperature swing in the hive gets smaller as brood grows. Supports the stability factor. |
| American Bee Journal, sensor grid | A sensor counts as over brood at ≥ 93 °F (34 °C) with a daily standard deviation ≤ 2 °F. Warns that where outdoor temperatures reach that level, temperature alone is unreliable. Supports using the outdoor temperature. |
| Cook et al. 2022 | Sensors nearest the centre of the hive track colony strength best. Empty hives ran about 5.5 °C cooler, with larger swings. Supports the colony warming constant. |

### 2.3 Sensor placement

- **On top of the frames** (BroodMinder's standard placement, on the top bars near the middle of
  the brood box): heat rises from the brood below. The temperature falls off gradually as the
  brood nest shrinks or moves away, so the reading is graded with brood size.
- **In the comb**, between frames at brood height: the sensor reads about 35 °C whenever brood
  surrounds it, however big the brood nest is (Godeau et al.). The reading shows whether the
  brood nest reaches the sensor: high for most of the season, low during a brood break, after
  losing the queen, or when the brood nest shrinks in autumn.


## 3. Requirements

Each requirement has an ID for traceability to the [verification](#14-verification) section.

### 3.1 Functional

| ID | Requirement |
|---|---|
| R1 | Hives with an in-hive temperature sensor get a Brood sensor: BroodMinder-T (models 41, 47) and BroodMinder-TH (models 42, 56). Other models (scales, hubs, SubHub, BeeDar, DIY, unknown) get no Brood sensor and no brood settings. |
| R2 | The estimate uses only the hive temperature and an outdoor temperature. It needs no scale and no humidity. |
| R3 | The estimate covers a rolling window of the last 24 complete hours and is updated every hour. |
| R4 | An estimate requires at least 18 hours in the window with both a hive and an outdoor temperature. |
| R5 | The Brood sensor exists before an outdoor temperature is available. Without an estimate it shows unknown, with a `status` attribute saying why. |
| R6 | The outdoor temperature source is a per-hive setting: a temperature sensor or a weather entity. |
| R7 | When the setting is empty, the outdoor temperature is found automatically: Met.no's *Forecast Home* weather entity, or else the only weather entity if there is exactly one. |
| R8 | A newly added or removed weather entity is picked up without restarting Home Assistant. |
| R9 | When there is no outdoor temperature, the user is told in a place they will see: a repair in Settings > System > Repairs, plus a warning in the log. A debug log alone is not enough. |
| R10 | An outdoor temperature in °F or K is converted to °C. A value without a temperature unit is not used. |
| R11 | The sensor position is a per-hive setting: on top of the frames (default) or in the comb. It changes the estimate as described in [6.3](#63-hourly-score). |
| R12 | The collected hours survive a restart of Home Assistant and a reload of the hive. A crash or power loss loses at most the hour in progress. |
| R13 | Removing a hive deletes its stored brood history. |
| R14 | Hives configured before this feature (no model stored) get their Brood sensor and settings after their first advertisement, without user action. |
| R15 | A Brood sensor on the hive's device keeps the device name and model the other sensors use, also when it is created before the hive has advertised. |

### 3.2 Non-functional

| ID | Requirement |
|---|---|
| N1 | Local only: no cloud service, API key or internet access of its own. The integration stays `local_push`. (Met.no itself fetches its forecast over the internet.) |
| N2 | No new Python requirements in `manifest.json`. |
| N3 | Bounded resources: memory and the storage file don't grow over time. |
| N4 | Works anywhere in the world: no assumption about hemisphere, season, climate or unit system. Hot climates are handled by showing unknown rather than a wrong value. |
| N5 | Defaults suit BroodMinder's documented standard placement, because the integration is published through HACS. |
| N6 | The algorithm is a pure function without Home Assistant dependencies, so it is unit-testable and can replay exported history. |

## 4. Design decisions

| ID | Decision | Rationale | Alternatives rejected |
|---|---|---|---|
| D1 | Temperature only, no scale | BroodMinder's own brood level comes from the T/TH temperature; a scale isn't needed. | Weight-based estimate. |
| D2 | Outdoor temperature from a Home Assistant entity | Local, reuses what Home Assistant already has, works with any weather integration or local sensor. | Ask for a location and call a weather API: adds a cloud dependency, API keys and failure modes, and duplicates Met.no. |
| D3 | Default: Met.no *Forecast Home*, else the only weather entity | Home Assistant onboarding creates Met.no's home entry on every install type; it follows the home location and elevation. The single-entity fallback covers users who replaced Met.no. With several weather entities, guessing is avoided. | Met.no only (forces users with another weather integration to add Met.no); the first weather entity (arbitrary). |
| D4 | Settings per hive | Each hive is its own config entry; Home Assistant has no integration-wide settings screen. Per hive also supports out-apiaries with their own outdoor sensor. Empty means automatic, so most users never touch it. | One integration-wide setting: needs an extra non-device config entry or settings copied into every entry. |
| D5 | No humidity | None of the studies use it; model T has no humidity, so T and TH would behave differently; in-hive humidity depends on nectar drying and ventilation as much as on brood. | Outdoor or in-hive humidity as an input. |
| D6 | Rolling 24 hours, updated hourly | Each value covers a full day-night cycle, so there is no daily artefact, and there is no wait until midnight. | Once a day after midnight, like BroodMinder. |
| D7 | Lower bound depends on the sensor position: 30 °C on top of the frames, 32 °C in the comb | In simulation the in-comb bound of 32 °C (bottom of the brood range) separates a brood break much better (8% instead of 26%). On top of the frames the temperature runs cooler, so 30 °C fits. | One bound for all placements: one of the two groups gets worse numbers. |
| D8 | Use the hive's last temperature while the hive is in range | Home Assistant drops advertisements whose data hasn't changed, so the time of the last update doesn't show whether the hive is still there. The coordinator's availability does. | Require an advertisement within the last 15 minutes. |
| D9 | Store the model id in the config entry | The Brood sensor and settings can then exist before the hive advertises, and `async_supports_options_flow` doesn't need a device registry lookup. | Look up the model in the device registry. |
| D10 | Own storage file with hourly sums | Works whether or not the recorder records the hive's sensors, is simple to test and stays small. | Rebuild the window from the recorder's history at startup. |
| D11 | Store the hours once an hour, when an hour completes | The first implementation used a 15-minute delayed save, but Home Assistant's delayed save is a debounce: calls every 5 minutes kept postponing it, so nothing reached disk until a clean stop. Saving per completed hour loses at most the hour in progress. | Save on every sample (12 writes an hour); save only at shutdown (loses data on a crash). |
| D12 | The shared repair waits until Home Assistant is fully started (`CoreState.running`) | Other integrations' weather entities may not exist during startup; avoids a false repair at every restart. `hass.is_running` is not enough: it is also true while starting. | Raise at once at setup. |
| D13 | Hive input is the *Temperature* field, not *Realtime Temp* | Temperature is sent by all T and TH models; Realtime Temp only by models 47 and 56. Hourly averaging makes the difference irrelevant. | Realtime Temp where available. |
| D14 | The Brood sensor stays available when the hive is out of range | It is an estimate over the last 24 hours, not a live reading; hours without hive data simply drop out of the window. | Follow the hive's availability. |
| D15 | Also store the hours at Home Assistant's final write | Home Assistant doesn't unload config entries when it stops, so without this a clean restart lost the samples of the hour in progress since its first save. | Rely on a pending delayed save: the hourly save runs at once, so none is pending at shutdown. |
| D16 | Estimate from the stored hours as soon as the hive is set up | The first sample waits until Home Assistant has started (D12). Without this, every restart showed unknown with `no_outdoor_temperature` until then, a false gap in history and statistics. | Wait for the first sample. |

## 5. Data collection

### 5.1 Sampling

Every 5 minutes (`BROOD_SAMPLE_INTERVAL`), and once when Home Assistant has started (or right
away when the hive is set up in a running Home Assistant), the tracker of each hive takes a
sample:

1. Resolve the outdoor temperature entity ([7.1](#71-source)).
2. Read the outdoor temperature in °C ([7.2](#72-reading-and-units)), or none.
3. Take the hive temperature: the Temperature of the latest parsed advertisement, but only if the
   hive is available (`PassiveBluetoothProcessorCoordinator.available`), otherwise none.
4. Add both to the bucket of the current hour. A missing temperature is skipped, not counted.
5. Drop buckets older than 48 hours (`BROOD_HISTORY_HOURS`).
6. If this sample started a new hour, store all buckets ([11.1](#111-brood-history-file)).
7. Recompute the estimate over the window ([5.3](#53-window)) and update the repairs.
8. Update the Brood sensor's state.

The hive temperature is updated on every parsed advertisement; an advertisement without a valid
temperature sets it to none.

When the hive is set up, the estimate is computed once from the stored buckets, before the first
sample (D16).

### 5.2 Hourly buckets

A bucket holds running sums for one hour:

| Field | Meaning |
|---|---|
| `hour` | Start of the hour, seconds since the Unix epoch: `floor(timestamp / 3600) × 3600` |
| `hive_sum`, `hive_count` | Sum and number of hive temperature samples, °C |
| `outdoor_sum`, `outdoor_count` | Sum and number of outdoor temperature samples, °C |

The hour's mean is `sum / count`, or none when `count` is 0. Buckets are aligned to UTC hours;
since the window is rolling, local time zones don't matter.

### 5.3 Window

With `current_hour` the start of the hour containing *now*, the window contains the buckets with

```
current_hour − 24 × 3600  ≤  hour  <  current_hour
```

that have both a hive and an outdoor mean. The hour in progress is excluded, so the estimate
changes once an hour, when an hour completes. The window has at most 24 hours (`n` below).

## 6. Algorithm

### 6.1 Symbols and constants

| Symbol | Constant in `const.py` | Value | Meaning |
|---|---|---|---|
| `T_in,h`, `T_out,h` | | | Mean hive and outdoor temperature of hour *h*, °C |
| `T_brood` | `BROOD_TEMP_C` | 35.0 °C | Temperature the colony keeps the brood nest at |
| `T_edge` | `BROOD_EDGE_TEMP_C` | 30.0 °C on top of the frames, 32.0 °C in the comb | Below this an hour counts as no brood |
| `ΔT_colony` | `COLONY_WARMING_C` | 4.0 °C | How much warmer than outdoors a colony keeps the hive without raising brood |
| `span_full` | `FULL_WEIGHT_SPAN_C` | 5.0 °C | An hour counts fully when its reference is at least this far below `T_brood` |
| `r_stable` | `STABLE_SWING_RATIO` | 0.2 | A hive swinging at most this share of the outdoor swing counts as fully stable |
| `swing_min` | `MIN_OUTDOOR_SWING_C` | 3.0 °C | Below this outdoor swing (overcast day) stability is not judged |
| `n_min` | `BROOD_MIN_HOURS` | 18 | Hours in the window needed for an estimate |
| | `BROOD_WINDOW_HOURS` | 24 | Window length in hours |

`clamp(x) = min(1, max(0, x))`.

### 6.2 Overview

```
brood % = round(100 × L × S)
```

`L` (level, 0..1) says how close the colony keeps the hive to brood temperature, compared with
what the weather alone would give. `S` (stability, 0..1) lowers the result when the hive
temperature swings along with the outdoor temperature.

### 6.3 Hourly score

For every hour *h* in the window:

```
T_ref,h  = max(T_out,h + ΔT_colony, T_edge)      reference: the hive without brood
span_h   = T_brood − T_ref,h                      room between the reference and 35 °C
```

If `span_h ≤ 0`, the hour is skipped: it was so warm outdoors (`T_out,h ≥ 31 °C`) that brood
temperature in the hive says nothing. Otherwise:

```
w_h = clamp(span_h / span_full)                   weight: warm hours count less
s_h = clamp((T_in,h − T_ref,h) / span_h)          score: share of the way to 35 °C
```

The reference is never below `T_edge`. That keeps a warm broodless winter cluster (for example
20 °C with −2 °C outdoors) from scoring: a hive temperature below the edge of the brood range
is no brood near the sensor, however far above outdoors it is. The position setting only
changes `T_edge`.

### 6.4 Level

```
L = Σ (w_h × s_h) / Σ w_h
```

If `Σ w_h = 0` (every hour skipped), there is no estimate: status `too_hot`.

### 6.5 Stability

The swing of a series is the difference between its 95th and 5th percentile, which ignores a
single odd hour: `swing(x) = P95(x) − P5(x)`, computed with
`statistics.quantiles(x, n=20, method="inclusive")` (linear interpolation; the first and last of
the 19 cut points).

```
if swing(T_out) < swing_min:
    S = 1                                          flat weather: stability not judged
else:
    S = clamp((1 − swing(T_in) / swing(T_out)) / (1 − r_stable))
```

A hive swinging at most 20% of the outdoor swing gets `S = 1`; a hive swinging as much as
outdoors gets `S = 0`.

### 6.6 Result

| Condition | Status | Brood % |
|---|---|---|
| Fewer than 18 hours in the window | `not_enough_data` | unknown |
| `Σ w_h = 0` | `too_hot` | unknown |
| Otherwise | `ok` | `round(100 × L × S)`, an integer 0 to 100 (Python `round`, halves to even) |

### 6.7 Worked examples

Steady day, hive 33.5 °C, outdoors 20 °C every hour (no outdoor swing, so `S = 1`):

- On top of the frames: `T_ref = max(24, 30) = 30`, `span = 5`, `s = 3.5 / 5 = 0.7` → **70%**
- In the comb: `T_ref = max(24, 32) = 32`, `span = 3`, `s = 1.5 / 3 = 0.5` → **50%**

Stability: a hive temperature that follows half the outdoor swing gives
`S = (1 − 0.5) / (1 − 0.2) = 0.625`.

### 6.8 Reference values

Synthetic days: the outdoor temperature follows a cosine with its minimum at 04:00 and maximum
at 16:00, and the hive temperature follows the formula given. These are the values the
implementation produces; they are the baseline for checking changes to the constants.

| Scenario | Outdoor °C | Hive °C (formula) | Top of frames | In comb |
|---|---|---|---|---|
| Full brood | 12 to 25 | 35.0 + 0.3·sin(hour) | 98% | 97% |
| Partial brood | 12 to 25 | 33.5 + 0.12·(T_out − 18.5) | 70% | 50% |
| Small brood nest far from the sensor | 12 to 25 | 31.0 + 0.35·(T_out − 18.5) | 21% | 8% |
| No brood | 12 to 25 | T_out + 6 | 0% | 0% |
| No brood, heatwave | 24 to 38 | min(T_out + 3, 36) | 0% | 0% |
| Full brood, heatwave | 24 to 38 | 35.2 + 0.05·(T_out − 31) | 98% | 98% |
| Winter cluster, no brood | −2 to 6 | 18 + 0.3·T_out | 0% | 0% |
| Winter, brood restarting | −2 to 6 | 31 + 0.2·T_out | 28% | 1% |
| Brood around an in-comb sensor | 12 to 25 | 34.8 + 0.2·sin(hour) | 96% | 94% |
| Brood break, bees present | 15 to 27 | 31.5 + 0.25·(T_out − 21) | 26% | 8% |

The unit tests assert ranges for these scenarios (for example full brood ≥ 90%, no brood ≤ 5%)
rather than exact values, so calibration can change the constants without rewriting tests. The
two worked examples are asserted exactly.

## 7. Outdoor temperature

### 7.1 Source

At every sample:

1. If the hive's *Outdoor temperature* setting is set, that entity is used.
2. Otherwise, Met.no's weather entity for the home location: found in the entity registry by
   platform `met` and unique ID `home` (so renaming it doesn't matter), unless it is disabled.
3. Otherwise, if exactly one `weather` entity has a state, that one.
4. Otherwise there is no source: the shared repair is raised ([10.1](#101-no-weather-entity)).

The resolved entity is shown in the sensor's `outdoor_entity` attribute.

### 7.2 Reading and units

| Entity | Value | Unit |
|---|---|---|
| `weather.*` | attribute `temperature` | attribute `temperature_unit` |
| any other domain (temperature sensor) | the state | attribute `unit_of_measurement` |

- State `unavailable` or a missing entity: no value.
- A weather entity whose state (its condition) is `unknown` still gives its temperature.
- The unit must be °C, °F or K, otherwise no value. The value is converted to °C with Home
  Assistant's `TemperatureConverter`.
- A value that isn't a number (for example a sensor state `unknown`): no value.

### 7.3 Accuracy notes

Met.no gives a forecast for the home coordinates, not a measurement. Home Assistant passes the
home elevation; without it Met.no uses its own coarse terrain model. Met.no is refreshed every
55 to 65 minutes, which is enough for hourly means. Hives far from home should use a local
outdoor sensor.

## 8. Configuration

### 8.1 Hive settings (config entry options)

Shown as **Configure** on the hive in Settings > Devices & services > BroodMinder, only when the
entry's model is 41, 42, 47 or 56. Saving changed settings reloads the hive
(`OptionsFlowWithReload`); the stored hours are kept.

| Key | Label | Type | Values | Default | Effect |
|---|---|---|---|---|---|
| `sensor_position` | Sensor position | required, select (list) | `top_of_frames`: On top of the frames (BroodMinder's standard placement); `in_comb`: In the comb, between frames at brood height | `top_of_frames` | `T_edge` 30 or 32 °C |
| `outdoor_entity` | Outdoor temperature | optional, entity selector | a `sensor` with device class `temperature`, or a `weather` entity | empty | Empty: automatic ([7.1](#71-source)). The selector filters the choice but doesn't check that the entity exists. |

### 8.2 Config entry data

| Key | Set | Value |
|---|---|---|
| `model` | at Bluetooth discovery, from byte 0 of the BroodMinder manufacturer data; for older entries, from the first parsed advertisement | the numeric model id |

The address stays the entry's unique ID. If discovery sees an empty payload, no model is stored
and it is filled in from the first advertisement.

### 8.3 Constants

All tunable values are in [`const.py`](custom_components/broodminder/const.py) and listed in
[6.1](#61-symbols-and-constants), plus:

| Constant | Value | Meaning |
|---|---|---|
| `BROOD_SAMPLE_INTERVAL` | 5 minutes | Sampling interval |
| `BROOD_HISTORY_HOURS` | 48 | Hours kept in memory and storage |
| `BROOD_STORAGE_VERSION` | 1 | Storage format version |
| `OUTDOOR_UNAVAILABLE_ISSUE_AFTER` | 3 hours | How long the outdoor temperature may be missing before the per-hive repair |
| `MET_DOMAIN`, `MET_HOME_UNIQUE_ID` | `met`, `home` | How Met.no's home weather entity is recognised |

## 9. Brood sensor entity

| Property | Value |
|---|---|
| Name | Brood (entity name on the hive's device) |
| Entity ID | `sensor.<device name>_brood`, for example `sensor.broodminder_th_00_00_01_brood` |
| Unique ID | `<bluetooth address>-brood` |
| Device | the hive's device, matched by its Bluetooth connection; created with the same name (`BroodMinder-<model name> <last three octets>`) and model name as the other sensors |
| State | integer percentage 0 to 100, or unknown |
| Unit, state class | `%`, `measurement` (so Home Assistant keeps long-term statistics) |
| Icon | `mdi:hexagon-multiple` |
| Availability | always available while the hive is loaded (D14) |
| Updates | after every sample; the value changes at most once an hour |

Attributes:

| Attribute | Value |
|---|---|
| `status` | `ok`, `not_enough_data`, `too_hot` or `no_outdoor_temperature` (precedence below) |
| `level` | `L`, rounded to 2 decimals, or none |
| `stability` | `S`, rounded to 2 decimals, or none |
| `hours_used` | number of hours in the window with both temperatures |
| `outdoor_entity` | the entity ID in use, or none |
| `sensor_position` | `top_of_frames` or `in_comb` |

Status precedence: if there is no estimate **and** the latest sample had no outdoor temperature,
`no_outdoor_temperature`; otherwise the algorithm's status. Before the first sample there is no
latest sample, so the algorithm's status is shown. An estimate still based on enough past hours
stays `ok` during a short outdoor outage.

## 10. Repairs and logging

Both repairs have severity *warning*, are not fixable from the repair dialog, and are not
persistent: they are not kept across a restart, and are raised again when the condition still
holds. Each logs one warning when it is raised. The texts are in
[`translations/en.json`](custom_components/broodminder/translations/en.json).

### 10.1 No weather entity

- Issue ID: `no_weather_entity`, one for the whole integration.
- Raised when Home Assistant is fully started and at least one loaded hive in automatic mode
  found no outdoor temperature source ([7.1](#71-source)).
- Withdrawn when no such hive remains: a weather entity appears, the hives get a configured
  outdoor entity, or they are unloaded.
- Evaluated at every sample of every hive and whenever a hive stops.
- Text: set the home location and add the Met.no integration, or choose an outdoor temperature in
  each hive's settings; with several weather entities and no Met.no *Forecast Home*, choose one.
- Log: `No weather entity for the brood estimate: add the Met.no integration, or choose an
  outdoor temperature in the settings of each BroodMinder hive`

### 10.2 Outdoor temperature unavailable

- Issue ID: `outdoor_temperature_unavailable_<config entry id>`, one per hive.
- Raised when the hive has an outdoor source and has not read a temperature from it for 3 hours
  or more. The 3 hours are counted from the last successful read, from when the source changed,
  or from when the hive was loaded, whichever is latest.
- Withdrawn at the next successful read, or when the hive unloads.
- Placeholders: `hive` (the device name as the user sees it: their own name for the device, else
  the device name, else the entry title) and `entity_id`.
- Log: `Outdoor temperature <entity> for the brood estimate of <hive> has been unavailable since
  <time>`

## 11. Persistence and resource use

### 11.1 Brood history file

| Property | Value |
|---|---|
| Location | `.storage/broodminder.brood.<config entry id>`, one file per hive |
| Format | Home Assistant `Store`, version 1: a list of buckets ([5.2](#52-hourly-buckets)) sorted by hour, JSON indented by 2 |
| Size | about 8.3 KB at most (48 hours plus the current one); it doesn't grow |
| Written | when a sample starts a new hour; when the hive unloads (reload, settings change, removal); at Home Assistant's final write when it stops (D15) |
| Read | when the hive is set up |
| Deleted | when the hive is removed |
| Write volume | about 24 writes a day per hive, plus one per restart; about 200 KB a day or 6 MB a month |

The 5-minute samples are never written individually, only the hourly sums.

### 11.2 Other storage

| Data | Where | Written |
|---|---|---|
| Settings and model | `.storage/core.config_entries` | when settings are saved; once when the model is stored |
| Repairs | `.storage/repairs.issue_registry` | when a repair appears or disappears |
| Brood state and attributes | recorder database | when the value or an attribute changes, about once an hour; unchanged updates only refresh the existing row's last-reported time |
| Statistics | recorder database | 5-minute statistics and hourly long-term statistics, because the state class is `measurement` |

Rough recorder estimates per hive, not measured: states about 10 KB a day, purged after the
recorder's retention (10 days by default), so about 100 KB steady; 5-minute statistics about
30 KB a day, also purged, about 300 KB steady; hourly statistics about 2 to 3 KB a day, kept
forever, about 1 MB a year.

### 11.3 Memory

About 15 KB per hive for the buckets (measured), constant over time.

## 12. Lifecycle

| Event | Behaviour |
|---|---|
| Discovery of a new device | Entry created with `model`. For T/TH: tracker started, Brood sensor created right away (unknown, `not_enough_data` or `no_outdoor_temperature`). |
| Setup of an existing T/TH entry | Stored buckets loaded and the estimate computed from them, so it is available immediately if the stored hours suffice, also while Home Assistant is starting; first sample when Home Assistant has started, or right away if it is running. |
| Entry without `model` (created before 0.5.0) | No Brood sensor and no settings at first. The first parsed advertisement stores the model; for T/TH the hive reloads once and gets them. |
| Settings saved with changes | Hive reloads with the new settings; buckets kept. Saving without changes doesn't reload. |
| Unload | Sampling stops, buckets saved, the hive's unavailable repair withdrawn, the shared repair re-evaluated. |
| Removal | Unload, then the history file is deleted. |
| Home Assistant restart | All buckets, including the hour in progress, written at the final write; repairs not kept; the per-hive repair can only reappear after 3 hours. |
| Crash or power loss | At most the hour in progress is lost. |

## 13. Calibration

The constants are starting values chosen from the literature and checked with the synthetic
scenarios in [6.8](#68-reference-values); they have not been fitted to real hives. BroodMinder's
own brood level wasn't available for comparison (the Bees app showed "no computed data").

Plan:

1. Record at each inspection: date, number of frames with brood per box, and for an in-comb
   sensor whether the combs on either side of it have brood.
2. Export the hive and outdoor temperature history from Home Assistant (History > download data).
3. Replay the export through `estimate_brood()` and compare with the inspection notes.
4. Tune, in order of expected impact: `COLONY_WARMING_C`, `BROOD_EDGE_TEMP_C`,
   `STABLE_SWING_RATIO`, `FULL_WEIGHT_SPAN_C`, `MIN_OUTDOOR_SWING_C`. Update the reference table
   in [6.8](#68-reference-values) and keep the range tests passing.

In temperate climates the low end (broodless, about 0%) can be checked in winter; the high end
needs the spring build-up.

## 14. Verification

### 14.1 Automated tests

Run with `scripts/test`; `scripts/lint` must be clean.

| Requirement | Tests |
|---|---|
| R1 | `test_GIVEN_t_and_scale_WHEN_discovered_THEN_only_t_gets_brood_sensor_and_settings`, `test_GIVEN_only_a_scale_WHEN_no_weather_entity_THEN_no_repair` |
| R2, R11, algorithm ([6](#6-algorithm)) | `test_GIVEN_day_on_top_of_frames_WHEN_estimate_THEN_brood_in_expected_range`, `test_GIVEN_brood_around_comb_sensor_WHEN_estimate_THEN_brood_high`, `test_GIVEN_brood_break_at_comb_sensor_WHEN_estimate_THEN_in_comb_reads_low`, `test_GIVEN_steady_day_WHEN_estimate_THEN_level_is_share_of_way_to_brood_temperature`, `test_GIVEN_hive_swinging_half_of_outdoors_WHEN_estimate_THEN_stability_reduced`, `test_GIVEN_every_hour_too_hot_WHEN_estimate_THEN_too_hot` |
| R3, R4 | `test_GIVEN_stored_hours_WHEN_brood_window_THEN_last_24_complete_hours_with_both`, `test_GIVEN_too_few_hours_WHEN_estimate_THEN_not_enough_data`, `test_GIVEN_samples_WHEN_added_to_hour_THEN_means_skip_missing_temperatures`, `test_GIVEN_timestamp_WHEN_hour_start_THEN_rounded_down_to_hour`, `test_GIVEN_hive_held_at_35_WHEN_hours_pass_THEN_brood_estimated_and_kept_on_reload` |
| R5, R9 | `test_GIVEN_no_weather_entity_WHEN_hive_set_up_THEN_brood_unknown_and_repair_raised`, `test_GIVEN_no_weather_repair_WHEN_hive_unloaded_THEN_repair_gone`, `test_GIVEN_outdoor_sensor_unavailable_WHEN_3_hours_pass_THEN_repair_until_back` |
| R6, R11 settings | `test_GIVEN_hive_WHEN_brood_settings_saved_THEN_hive_reloads_with_them` |
| R7 | `test_GIVEN_met_home_and_other_weather_WHEN_hive_set_up_THEN_met_home_used`, `test_GIVEN_several_weather_entities_without_met_home_WHEN_set_up_THEN_repair_raised` |
| R8 | `test_GIVEN_no_weather_repair_WHEN_weather_entity_added_THEN_used_and_repair_gone` |
| R10 | `test_GIVEN_outdoor_state_WHEN_read_THEN_temperature_in_celsius`, `test_GIVEN_hive_held_at_35_WHEN_hours_pass_THEN_brood_estimated_and_kept_on_reload` (outdoor sensor in °F) |
| R12 | `test_GIVEN_hive_sampling_WHEN_hour_completes_THEN_hours_stored_without_unload`, `test_GIVEN_hive_held_at_35_WHEN_hours_pass_THEN_brood_estimated_and_kept_on_reload`, `test_GIVEN_hour_in_progress_WHEN_home_assistant_stops_THEN_hours_stored` (D15) |
| D16 | `test_GIVEN_stored_hours_WHEN_home_assistant_starting_THEN_estimate_shown_at_once` |
| R13 | `test_GIVEN_hive_with_stored_hours_WHEN_removed_THEN_brood_history_deleted` |
| R14 | `test_GIVEN_entry_from_before_brood_WHEN_t_advertises_THEN_brood_sensor_added` |
| R15 | entity IDs `sensor.broodminder_th_00_00_01_brood` and `sensor.broodminder_t_00_00_03_brood` in the tests above |
| D8 | `test_GIVEN_hive_held_at_35_WHEN_hours_pass_THEN_brood_estimated_and_kept_on_reload` sends identical advertisements, which Home Assistant drops after the first |

Not covered by automated tests: N1 to N4 (by review), the startup guard of the shared repair
(D12), and real Bluetooth reception.

### 14.2 Manual checks on real hardware

The devcontainer has no Bluetooth adapter, so these need a real Home Assistant with the hives in
range:

1. A T/TH hive has **Configure** with both settings; a scale doesn't.
2. Right after installing, the Brood sensor shows unknown with `status: not_enough_data` and
   `outdoor_entity: weather.forecast_home` (or your weather entity).
3. After about 18 to 19 hours it shows a percentage with `status: ok`.
4. `.storage/broodminder.brood.<entry id>` exists, about 8 KB, and its modification time changes
   about once an hour.
5. After a restart the value is back right away.
6. Disabling the weather entity raises *BroodMinder brood estimate has no outdoor temperature*
   in Repairs within 5 minutes; enabling it again withdraws it.
7. A configured outdoor sensor that stays unavailable raises the per-hive repair after 3 hours.
8. The value is plausible: high with brood around the sensor, dropping during a brood break.

## 15. Known limitations

- The sensor measures one point; the percentage is relative, not frames of brood, and below
  about 20% it is rough.
- In the comb, the estimate shows whether the brood nest reaches the sensor, not how big it is.
- Hours with an outdoor temperature of 31 °C or more are ignored. In climates that stay that warm
  day and night, the sensor often shows unknown.
- The estimate lags up to an hour, because only complete hours are used.
- A new hive, or one whose history was lost, needs about 18 hours before the first value.
- The automatic outdoor temperature is a forecast for the home location; accuracy depends on the
  home elevation, and distant apiaries need a local sensor.
- With several weather entities and no Met.no *Forecast Home*, each hive needs a configured
  outdoor entity.
- The constants are not calibrated yet ([13](#13-calibration)).

## 16. References

- BroodMinder, Working with Temperature & Brood:
  <https://doc.mybroodminder.com/50_mybroodminder_v5c_temperature/>
- BroodMinder, BroodMinder TH & T (placement, SwarmMinder):
  <https://doc.mybroodminder.com/31_sensors_T_TH/>
- BroodMinder, Working with Weather: <https://doc.mybroodminder.com/50_mybroodminder_v5h_weather/>
- Godeau U. et al., Brood thermoregulation effectiveness is positively linked to the amount of
  brood but not to the number of bees in honeybee colonies (preprint, EcoEvoRxiv):
  <https://ecoevorxiv.org/repository/object/3755/download/10297>
- Meikle W. G. et al. 2015, temperature amplitude and brood, Apidologie 47:
  <https://link.springer.com/article/10.1007/s13592-015-0370-1>
- American Bee Journal, Monitoring honey bee colony activities with a temperature sensor grid,
  part 2:
  <https://americanbeejournal.mydigitalpublication.com/articles/monitoring-honey-bee-colony-activities-with-a-temperature-sensor-grid-part-2>
- Cook D. et al. 2022, Temperature Sensing and Honey Bee Colony Strength, Journal of Economic
  Entomology 115(3): <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9175291/>
- Met.no Locationforecast documentation:
  <https://api.met.no/weatherapi/locationforecast/2.0/documentation>
