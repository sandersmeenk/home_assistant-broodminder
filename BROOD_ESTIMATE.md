# Brood estimate: specification

Technical specification of the brood estimate in the BroodMinder integration, and of the likely
brood break built on it: requirements, design decisions, the algorithms with their formulas and
constants, configuration, persistence and how to verify it. It describes the implementation as
of version 0.5.0.

- Status: implemented, constants not yet calibrated against real hives (see
  [Calibration](#14-calibration))
- Code: [`brood.py`](custom_components/broodminder/brood.py) (algorithms),
  [`brood_tracker.py`](custom_components/broodminder/brood_tracker.py) (sampling, outdoor
  temperature, storage, repairs), [`config_flow.py`](custom_components/broodminder/config_flow.py)
  (settings), [`sensor.py`](custom_components/broodminder/sensor.py) (entities),
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
7. [Likely brood break](#7-likely-brood-break)
8. [Outdoor temperature](#8-outdoor-temperature)
9. [Configuration](#9-configuration)
10. [Brood sensor entity](#10-brood-sensor-entity)
11. [Repairs and logging](#11-repairs-and-logging)
12. [Persistence and resource use](#12-persistence-and-resource-use)
13. [Lifecycle](#13-lifecycle)
14. [Calibration](#14-calibration)
15. [Verification](#15-verification)
16. [Known limitations](#16-known-limitations)
17. [References](#17-references)

## 1. Purpose

BroodMinder's Bees app and MyBroodMinder show a daily *brood level*: a percentage where 0% means
no brood and 100% a hive full of brood. BroodMinder computes it in its cloud and doesn't publish
the method. This integration provides a comparable estimate locally, inside Home Assistant, from
data it already has: the in-hive temperature that BroodMinder-T and -TH sensors broadcast over
Bluetooth, and an outdoor temperature from Home Assistant.

From the brood estimate, the integration also tells when a hive has likely been without brood
near the sensor for some days: a *likely brood break*. It helps time an oxalic acid trickle
treatment against varroa, which works best when there is no capped brood
([2.4](#24-brood-development-and-the-window-without-capped-brood)).

Out of scope: weight (scales), humidity, colony strength (number of bees), frames of brood as an
absolute number, treatment advice (when, which product, dose), a predicted brood break from
beekeeping events such as caging the queen (D19), and any cloud service.

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

### 2.4 Brood development and the window without capped brood

Development of honey bee brood, in days after the egg is laid (Winston 1987). The times vary by
about a day with temperature and subspecies; worker cells are capped on day 8 or 9.

| | Egg | Open larva | Capped | Emerges |
|---|---|---|---|---|
| Worker | days 0 to 3 | days 3 to 9 | days 9 to 21 | day 21 |
| Drone | days 0 to 3 | days 3 to 10 | days 10 to 24 | day 24 |

Oxalic acid trickled between the combs reaches the varroa mites on adult bees, not those
reproducing in capped cells, so it works best when the colony has no capped brood.

When the queen stops laying on day 0 and starts again on day *x*:

```
day 0       queen stops laying (caged, swarmed, queenless, autumn)
day 9–10    last worker and drone cells capped
day 21      last workers emerge
day 24      last drones emerge       ← no capped brood from here
            … no brood: the colony stops keeping the hive at 35 °C, the Brood % falls …
day x       queen lays again         ← the colony heats the brood nest again, the Brood % rises
day x + 8   first new cells capped   ← no capped brood until here
```

What follows for this specification:

- The colony keeps capped brood at brood temperature until the last bee has emerged, so a drop in
  the brood estimate marks the end of the capped brood near the sensor. When the drop is seen,
  the window without capped brood is already open; it is not 21 to 24 days ahead.
- The window closes about 8 days after the queen lays again. A small new egg patch may not warm
  the sensor at once, so the temperature can't tell when the window closes (D19).
- "No capped brood 21 to 24 days after laying stopped" needs the day laying stopped. Temperature
  can't see it; the beekeeper knows it (caged queen, swarm, split).
- If the queen stops laying for less than about 21 days, new open brood appears before the last
  capped brood has emerged. The hive is never without brood and the brood estimate shows no
  break, although a short window without capped brood exists when laying stopped for more than
  about two weeks.


## 3. Requirements

Each requirement has an ID for traceability to the [verification](#15-verification) section.

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
| R13 | Removing a hive deletes its stored brood history, including its likely brood break. |
| R14 | Hives configured before this feature (no model stored) get their Brood sensor and settings after their first advertisement, without user action. |
| R15 | A Brood sensor on the hive's device keeps the device name and model the other sensors use, also when it is created before the hive has advertised. |
| R16 | Hives that get a Brood sensor also get a *Likely brood break since* sensor, on the same device and enabled by default. Other models get neither. |
| R17 | The Likely brood break since sensor shows when the current likely brood break started, as a date and time, and unknown when there is no likely brood break. It has no attributes. |
| R18 | A likely brood break starts once the Brood % has been at or below the low threshold for 48 hourly estimates, without an estimate above it in between. The start shown is the time of the first of those 48 estimates. |
| R19 | A likely brood break ends once the Brood % has been above the end level for 24 hourly estimates in a row. The end level is higher than the low threshold. |
| R20 | The low threshold and the end level depend on the sensor position (R11). They are constants, not settings. |
| R21 | Any low period counts, in any season, including the gradual autumn decline into the winter break. |
| R22 | Hours without an estimate neither count nor reset. After an outage without data of a day or longer with Home Assistant off, or of more than 30 hours with it running, a count in progress (R18, R19) starts over; a likely brood break that has started is kept. Between estimates this is more than 42 hours: the next estimate waits until the window has 18 hours again ([7.4](#74-rule)). |
| R23 | A likely brood break and the counts in progress survive a restart of Home Assistant and a reload of the hive. Each hourly estimate counts once, also across a restart. |
| R24 | A brood history file written by a development build of 0.5.0 (storage version 1) is migrated, keeping its hours. |
| R25 | A brood history file that can't be used (a newer version, invalid JSON, unexpected content or a failing migration) doesn't stop the hive from setting up: the hive starts with a clean brood history and a warning is logged (for invalid JSON, Home Assistant's own repair). |
| R26 | The brood history file carries its format version. Every change of the format increases it. A file with an older version is migrated to the current one; a file with a newer version, left by a later version of the integration before a downgrade, is replaced by a clean file. |
| R27 | A Home Assistant backup contains all data the brood estimate and the likely brood break need to continue: each hive's brood history (its hours and likely brood break), its settings and model, and the integration itself, also in a backup without the database. The brood history is in the state of its last hourly save: the samples taken since then, at most an hour's, aren't in the backup (D32). |
| R28 | Restoring a Home Assistant backup restores each hive's brood history as it was in the backup. The brood estimate and the likely brood break then continue from it as if Home Assistant had been off from the backup until the restore: the backup's hours still in the window count at once (D16), and the time in between is a gap as in R22. |
| R29 | A brood history file of any older storage version is migrated to the current one, also when the releases in between were never installed. For example, if 0.5.0 wrote version 2, 0.6.0 version 3 and 0.7.0 version 4, a user going from 0.5.0 straight to 0.7.0 gets the version 2 file migrated to version 4 at the first setup, keeping its hours and its likely brood break, as if 0.6.0 had been installed in between. |
| R30 | An outdoor temperature that isn't a finite number (`nan`, `inf`) is not used, like a missing one. Only finite numbers reach the hourly buckets and the brood history file. |
| R31 | A stored value of the wrong type (text, `null`, `true` or `false`, or a number that isn't finite where a number is expected) is unexpected content (R25): the hive starts with a clean brood history and a warning is logged. A whole number where a decimal is expected is accepted. |

### 3.2 Non-functional

| ID | Requirement |
|---|---|
| N1 | Local only: no cloud service, API key or internet access of its own. The integration stays `local_push`. (Met.no itself fetches its forecast over the internet.) |
| N2 | No new Python requirements in `manifest.json`. |
| N3 | Bounded resources: memory and the storage file don't grow over time. |
| N4 | Works anywhere in the world: no assumption about hemisphere, season, climate or unit system. Hot climates are handled by showing unknown rather than a wrong value. |
| N5 | Defaults suit BroodMinder's documented standard placement, because the integration is published through HACS. |
| N6 | The algorithms (brood estimate and likely brood break) are pure functions without Home Assistant dependencies, so they are unit-testable and can replay exported history. |

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
| D10 | Own storage file with hourly sums | Works whether or not the recorder records the hive's sensors, is simple to test and stays small. As a `Store` file in `.storage/` it is in every Home Assistant backup, also one without the database (R27). | Rebuild the window from the recorder's history at startup. |
| D11 | Store the hours once an hour, when an hour completes | The first implementation used a 15-minute delayed save, but Home Assistant's delayed save is a debounce: calls every 5 minutes kept postponing it, so nothing reached disk until a clean stop. Saving per completed hour loses at most the hour in progress. | Save on every sample (12 writes an hour); save only at shutdown (loses data on a crash). |
| D12 | The shared repair waits until Home Assistant is fully started (`CoreState.running`) | Other integrations' weather entities may not exist during startup; avoids a false repair at every restart. `hass.is_running` is not enough: it is also true while starting. | Raise at once at setup. |
| D13 | Hive input is the *Temperature* field, not *Realtime temp* | Temperature is sent by all T and TH models; Realtime temp only by models 47 and 56. Hourly averaging makes the difference irrelevant. | Realtime temp where available. |
| D14 | The Brood sensor stays available when the hive is out of range | It is an estimate over the last 24 hours, not a live reading; hours without hive data simply drop out of the window. | Follow the hive's availability. |
| D15 | Also store the hours at Home Assistant's final write | Home Assistant doesn't unload config entries when it stops, so without this a clean restart lost the samples of the hour in progress since its first save. | Rely on a pending delayed save: the hourly save runs at once, so none is pending at shutdown. |
| D16 | Estimate from the stored hours as soon as the hive is set up | The first sample waits until Home Assistant has started (D12). Without this, every restart showed unknown with `no_outdoor_temperature` until then, a false gap in history and statistics. | Wait for the first sample. |
| D17 | The hourly weight is the span, without a constant | The first version used `clamp(span / FULL_WEIGHT_SPAN_C)` with 5 °C. The span is never more than `35 − T_edge` (5 °C on top of the frames, 3 °C in the comb), so the clamp never applied and the weight was always `span / 5`. Since only the ratio between weights matters, the constant had no effect at 5 °C or above, yet was listed as one to tune. Removing it gives identical results. | Keep the constant and document that only values below 3 to 5 °C have an effect. |
| D18 | Stability uses all hours in the window, also those the level skips as too hot | Stability needs the full day-night cycle to see whether the hive follows the weather. Without the hot afternoon hours the outdoor swing shrinks (17.4 to 11.1 °C on a day from 18 to 36 °C) and on mild days could drop below `MIN_OUTDOOR_SWING_C`, so stability would no longer be judged. The cost: a hive with brood that overheats in a heatwave is marked down for hours the level ignores (see [16](#16-known-limitations)). | Use only the hours the level uses. |
| D19 | Detect the brood break from the temperature; no predicted treatment date | The temperature drop marks the end of the capped brood ([2.4](#24-brood-development-and-the-window-without-capped-brood)), so the window without capped brood is already open when the break is seen. A predicted date needs the day laying stopped (caged queen, swarm, split), which only the beekeeper knows; a date helper and a template in Home Assistant already do that sum. The end of the window can't be predicted either: a small new egg patch may not warm the sensor at once. | A per-hive "laying stopped" date with a predicted "no capped brood from" date; a "treatment window until" date from the end of the break. |
| D20 | A timestamp sensor, unknown without a likely break; no binary sensor, no attributes | The state alone tells whether there is a likely break and since when. Home Assistant shows a timestamp as "3 days ago", automations can compute the days from it, and past breaks stay visible in the history. | A binary sensor next to the timestamp; keeping the last start with an `ended` attribute; a sensor or attribute with the number of days (a daily update that adds no information). |
| D21 | "Likely" in the name | The sensor measures one point: a broodless hive and a small brood nest away from the sensor score the same ([6.8](#68-reference-values)). The name says it's a reason to check a frame, not a finding. | "Brood break started" or "Brood break since", with the uncertainty only in the README. |
| D22 | Thresholds per sensor position, as constants | In [6.8](#68-reference-values) a broodless hive whose bees keep warm scores 26% on top of the frames and 8% in the comb, while partial brood scores 70% and 50%: one threshold can't serve both. Constants, like the brood estimate's, tuned by calibration. | One threshold for both positions (hives with the sensor on top of the frames miss breaks); in-comb hives only; per-hive settings (more to explain, and nothing to base a choice on before calibration). |
| D23 | Confirm after 48 hourly estimates; show the time of the first | One estimate already covers 24 hours; two more days keep a cold spell, an inspection or a contracted cluster from starting a break. Showing the first low estimate counts the days from the drop rather than from the confirmation. The first low estimate rather than the start of its 24-hour window: by then the drop is measured, so a break is never shown as longer than the data says. | 24 estimates (false breaks); 72 (a day later for a real break); the time of confirmation (always 2 days late); the start of the first low estimate's window (up to 24 hours too early). |
| D24 | End at a higher level, held for 24 hours | The gap between the low threshold and the end level, and the 24 hours, keep a brief warm spell from ending a break and starting it again with a new start time. | End at the first estimate above the low threshold. |
| D25 | Any low period counts | The gradual autumn decline into the winter break is the classic time for an oxalic acid trickle. Requiring brood shortly before would miss it, and a hive set up during a break. | Count only a drop after a period with brood (for example 50% or more in the 2 weeks before). |
| D26 | Gaps hold, but a count in progress starts over after an outage of a day | Short gaps (a restart, an outdoor temperature outage, the hive briefly out of range) shouldn't reset anything. After a long gap (Home Assistant off, the hive moved, another version installed for a while), a count would join hours weeks apart: 30 low hours, 3 weeks away, then 18 low hours would start a break backdated by 3 weeks. A normal restart has no gap at all (D16). A break that has started is kept, and after a gap ends the normal way (R19). The rule measures the time between two estimates, which is longer than the outage: estimates stop once fewer than 18 hours of the window have data, and return only when 18 new hours have arrived (R4). So `gap_max` is 42 hours, an outage of 24 hours plus the 18 hours to refill the window. It was 24 hours at first, which reset a count after an outage of 7 hours with Home Assistant off (13 hours with it running), such as an update that failed overnight: a short gap treated as a long one. | Hold everything across any gap; reset everything after 3 days without estimates, including a break that has started (loses the start of a real break); 24 hours between estimates (resets after a 7-hour outage); measure from the last hour with data (the same 24 hours for every kind of outage, but another stored field and storage version, for outages of 24 to 30 hours only). |
| D27 | Store the likely brood break in the brood history file, as storage version 2 | One file and one write an hour, as before. Version 1 was only written by development builds of 0.5.0, so the migration only matters there; 0.4.0 and earlier never read the file ([12.4](#124-compatibility-between-versions)). | A second file per hive: no migration and any build can be installed and reverted, but a second write every hour per hive. |
| D28 | A brood history file that can't be read or migrated starts empty | Home Assistant's `Store` raises on a storage version it can't migrate, and the tracker loads the file during the hive's setup, so all the hive's sensors failed to set up, not just Brood. Losing up to 48 hours and the break state costs less. Protects every later change of the file format, for example when going back to an older version. | Fail the setup, as before. |
| D29 | Write the Likely brood break since state only when it changes | The tracker calls its listeners every 5 minutes. For the Brood sensor that refreshes the recorder row's last-reported time each time ([12.2](#122-other-storage)). The break changes a few times a year, so writing only on change leaves the recorder idle. | Write on every sample, like the Brood sensor. |
| D30 | Every format change increases the major storage version; `minor_version` stays 1 | The version in the file is what makes migrations and downgrade detection possible (R26). Home Assistant's `Store` treats a file with the same major and another minor version as readable by any code with that major version, and uses it as it is. That only works for changes older code can ignore, and older code would drop the new fields at its next save without noticing. With one major version per change, every downgrade is detected and handled the same way. A newer file isn't kept as a backup: it holds at most 48 hours and the break state. | Minor versions for changes older code can ignore; keeping the newer file as a backup on a downgrade. |
| D31 | Likely brood break since is enabled by default, as a main sensor without entity category | It is the reason for the feature, and a disabled entity is easy to miss: users would have to find and enable it on every hive. While nothing changes it costs nothing (D29). Beekeepers who don't need it can disable it. | Disabled by default; the diagnostic entity category. |
| D32 | No backup platform: a backup holds the brood history of the last hourly save | Home Assistant saves no integration's storage before a backup; it only calls `async_pre_backup` of integrations with a `backup` platform. Without one, the backup lacks the samples since the last hourly save, at most 11. The hour in progress is in the backup with its first sample (the save comes after it, [5.1](#51-sampling)), so it still counts, from fewer samples. A restore loses the whole time between the backup and the restore, usually hours or days, so these minutes add little. | A `backup` platform whose `async_pre_backup` saves every hive's brood history, so the backup has the hour in progress: one more module and one more write per hive and backup. |
| D33 | Migrations are chained steps, one per format change, applied in order and kept for good | HACS doesn't make users install every release, and an installation left alone for months skips several. Home Assistant's `Store` calls `_async_migrate_func` once, with the file's version, and expects data in the code's version back. Each step turns version N − 1 into version N and runs for every file older than version N, not only for version N − 1, so a file of any older version passes through every later step in turn (R29). A new format adds one step after the others; existing steps aren't changed or removed, because a file of their version can still turn up, from an installation that skipped releases or from an old backup (R28). Each step is a few lines. | A migration from the previous version only (a file two versions old fails the migration and starts clean, losing its hours and likely brood break); a direct migration from every older version to the current one (all of them rewritten at every format change); removing steps after some releases (a user who skips them loses the brood history). |
| D34 | Check every stored field's type when the file is loaded, against the type its dataclass declares | `HourlyTemperatures(**data)` and `BroodBreak(**data)` accept any value. A `null` sum (how orjson writes NaN, which an outdoor state `nan` used to produce) failed later in the estimate at setup, outside the load guard: the hive's setup failed without a retry and the file was never replaced. Text in `since` failed in the sensor and left the hive without sensors. Checking at load keeps every bad file inside the R25 handling. | Catching errors wherever bad values are used; replacing bad values one by one with defaults (keeps a file of unknown origin). |
| D35 | Detect a newer major version in `BroodHistoryStore.async_load` as well as in the migration | Since Home Assistant 2026.3, `Store` raises `UnsupportedStorageVersionError` for a file with a newer major version before it calls `_async_migrate_func`, so the migration never sees it; older versions down to the minimum (2025.9) still pass it to the migration. Without catching it, the error escaped the R25 handling and the hive failed to set up with all its sensors. `async_load` turns it into the same `UnsupportedBroodHistoryError` the migration raises, so both Home Assistant versions behave and log the same: the newer major version alone, since Home Assistant's error doesn't carry the minor one (R26). The import falls back for Home Assistant before 2026.3 (`compat.py`). | Passing a higher `max_readable_version` to `Store` (not accepted by Home Assistant before 2026.3); catching every `HomeAssistantError` (would also hide other load errors behind a "newer version" warning). |

## 5. Data collection

### 5.1 Sampling

Every 5 minutes (`BROOD_SAMPLE_INTERVAL`), and once when Home Assistant has started (or right
away when the hive is set up in a running Home Assistant), the tracker of each hive takes a
sample:

1. Resolve the outdoor temperature entity ([8.1](#81-source)).
2. Read the outdoor temperature in °C ([8.2](#82-reading-and-units)), or none.
3. Take the hive temperature: the Temperature of the latest parsed advertisement, but only if the
   hive is available (`PassiveBluetoothProcessorCoordinator.available`), otherwise none.
4. Add both to the bucket of the current hour. A missing temperature is skipped, not counted.
5. Drop buckets older than 48 hours (`BROOD_HISTORY_HOURS`).
6. If this sample started a new hour, store all buckets ([12.1](#121-brood-history-file)).
7. Recompute the estimate over the window ([5.3](#53-window)) and update the repairs.
8. Count the estimate for the likely brood break ([7.1](#71-input)). The save of step 6 takes
   its data when it writes, after the sample, so it stores this count too.
9. Update the Brood sensor's state, and the Likely brood break since state if it changed.

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
w_h = span_h                                      weight: warm hours count less
s_h = clamp((T_in,h − T_ref,h) / span_h)          score: share of the way to 35 °C
```

The reference is never below `T_edge`. That keeps a warm broodless winter cluster (for example
20 °C with −2 °C outdoors) from scoring: a hive temperature below the edge of the brood range
is no brood near the sensor, however far above outdoors it is. The position setting only
changes `T_edge`.

The weight is the span itself (D17): an hour counts in proportion to the room the weather leaves
below 35 °C. Only the ratio between hours matters, because the level divides by the sum of the
weights. Up to `T_out,h = T_edge − ΔT_colony` (26 °C on top of the frames, 28 °C in the comb)
the reference is `T_edge`, so every such hour has the same weight; above it the weight falls to 0
at 31 °C. On a day that stays below that temperature the level is the plain mean of the scores.

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

Both swings are taken over all hours in the window, including the hours the level skips because
they were too hot ([6.3](#63-hourly-score)) (D18). While the hive behaves the same in hot and cool
hours, this gives the same `S` as the cool hours alone: for a day from 18 to 36 °C outdoors with
9 hours too hot, a hive following half the outdoor swing gets `S = 0.62` either way.

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

## 7. Likely brood break

The likely brood break follows the Brood % over the days: it starts when
the Brood % stays low for two days, and ends when it stays clearly higher for a day. Why a low
Brood % matters for treatment is in
[2.4](#24-brood-development-and-the-window-without-capped-brood).

### 7.1 Input

Each brood estimate with status `ok` is one input: its Brood % `p` and its time `h`, the
`current_hour` the estimate was computed for ([5.3](#53-window)), which is the end of its window.
The estimate changes once an hour, so there is at most one input an hour.

- Estimates with another status (`not_enough_data`, `too_hot`, `no_outdoor_temperature`) are no
  input; those hours are a gap.
- An estimate whose time was already counted (`h ≤ last_hour`) is skipped. The estimate at every
  5-minute sample, and the one computed from the stored hours when the hive is set up (D16),
  therefore count once.

### 7.2 Constants

| Symbol | Constant in `const.py` | Value | Meaning |
|---|---|---|---|
| `p_low` | `BROOD_BREAK_LOW_PERCENT` | 30% on top of the frames, 15% in the comb | At or below this, an estimate is low |
| `p_end` | `BROOD_BREAK_END_PERCENT` | 45% on top of the frames, 30% in the comb | Above this, an estimate counts towards the end of a break |
| `n_start` | `BROOD_BREAK_START_HOURS` | 48 | Low estimates that start a break |
| `n_end` | `BROOD_BREAK_END_HOURS` | 24 | Estimates in a row above `p_end` that end a break |
| `gap_max` | `BROOD_BREAK_MAX_GAP_HOURS` | 42 hours (`BROOD_WINDOW_HOURS` + `BROOD_MIN_HOURS`) | A longer time between two estimates restarts a count in progress: an outage of a day, plus the 18 hours the window needs to refill (D26) |

### 7.3 State

| Field | Meaning |
|---|---|
| `since` | Start of the likely brood break, in seconds since the Unix epoch, or none |
| `low_since` | Time of the first estimate of the low count in progress, or none |
| `low_count` | Low estimates counted since `low_since` |
| `end_count` | Estimates in a row above `p_end` during a break |
| `last_hour` | Time of the last counted estimate, or none |

The sensor shows `since`. The state is stored with the hours ([12.1](#121-brood-history-file)).

### 7.4 Rule

For each estimate `(h, p)`, with `p_low` and `p_end` for the hive's sensor position:

```
if last_hour is not none and h ≤ last_hour:          already counted
    skip
if last_hour is not none and h − last_hour > gap_max: long gap (D26)
    low_since, low_count, end_count = none, 0, 0
last_hour = h

if since is none:                                     no likely break
    if p ≤ p_low:
        if low_since is none:
            low_since = h
        low_count += 1
        if low_count ≥ n_start:
            since = low_since                         break starts, backdated (D23)
            low_since, low_count = none, 0
    else:
        low_since, low_count = none, 0                low count starts over
else:                                                 likely break
    if p > p_end:
        end_count += 1
        if end_count ≥ n_end:
            since, end_count = none, 0                break ends
    else:
        end_count = 0                                 end count starts over
```

- During a break, estimates between `p_low` and `p_end` keep the break and reset the end count
  (D24).
- After a break ends, the next low estimate starts a new count, and a new break gets a new start.
- When the sensor position changes (R11, the hive reloads), the thresholds of the new position
  apply from the next estimate; the state is kept.
- The rule only uses the successive estimates and their times, not the clock, so replaying
  exported history gives the same result as running live.
- An outage of `G` hours without data makes a longer gap between estimates. With Home Assistant
  off, the window still has `24 − G` hours when it starts again: up to `G` = 6 an estimate comes
  at once, and after a longer outage only once 18 new hours have arrived, `G + 19` hours after
  the last one (the last estimate before the outage doesn't include its own hour). With Home
  Assistant running, estimates continue from the hours left in the window for the first 6 hours,
  so the gap is `G + 12`. With `gap_max` = 42, a count continues after an outage of up to 23
  hours with Home Assistant off and 30 hours with it running (R22, D26).

### 7.5 Worked example

Sensor on top of the frames (`p_low` = 30%, `p_end` = 45%). The Brood % has been about 70% until
the last brood near the sensor emerged. Every hour has an estimate.

| Time of estimate (UTC) | Brood % | What happens | Sensor shows |
|---|---|---|---|
| until 10 June 11:00 | about 70 | | unknown |
| 10 June 12:00 | 24 | low count 1, `low_since` = 10 June 12:00 | unknown |
| 10 June 13:00 to 12 June 10:00 | 5 to 28 | low count 2 to 47 | unknown |
| 12 June 11:00 | 12 | low count 48: break starts | 10 June 12:00 |
| 12 June 12:00 to 20 June 07:00 | 3 to 30 | break continues | 10 June 12:00 |
| 20 June 08:00 to 21 June 05:00 | 32 to 40 | between `p_low` and `p_end`: break continues | 10 June 12:00 |
| 21 June 06:00 to 22 June 04:00 | 50 to 65 | end count 1 to 23 | 10 June 12:00 |
| 22 June 05:00 | 61 | end count 24: break ends | unknown |

Long gap: with a low count of 30 reached on 2 June and the next estimate on 22 June (Home
Assistant was off), the count starts over at that estimate; no break is backdated to 1 June.

### 7.6 How the reference scenarios count

The scenarios of [6.8](#68-reference-values), each repeated day after day:

| Scenario | Top of frames | Counts as | In comb | Counts as |
|---|---|---|---|---|
| Full brood | 98% | above end | 97% | above end |
| Partial brood | 70% | above end | 50% | above end |
| Small brood nest far from the sensor | 21% | low | 8% | low |
| No brood | 0% | low | 0% | low |
| No brood, heatwave | 0% | low | 0% | low |
| Full brood, heatwave | 98% | above end | 98% | above end |
| Winter cluster, no brood | 0% | low | 0% | low |
| Winter, brood restarting | 28% | low | 1% | low |
| Brood around an in-comb sensor | 96% | above end | 94% | above end |
| Brood break, bees present | 26% | low | 8% | low |

All broodless scenarios are low in both positions, and brood that reaches the sensor ends a
break. A small brood nest far from the sensor and brood restarting in winter are low as well: the
temperature can't tell them from no brood (D21, [16](#16-known-limitations)).

### 7.7 Likely brood break since sensor

| Property | Value |
|---|---|
| Name | Likely brood break since (entity name on the hive's device) |
| Entity ID | `sensor.<device name>_likely_brood_break_since`, for example `sensor.broodminder_th_00_00_01_likely_brood_break_since` |
| Unique ID | `<bluetooth address>-brood_break` |
| Device | the hive's device, as for the Brood sensor (R15) |
| Device class | `timestamp` |
| State | `since` as a date and time in UTC, or unknown |
| Unit, state class | none: a timestamp sensor has neither, so there are no long-term statistics |
| Attributes | none |
| Icon | `mdi:hexagon-multiple-outline` |
| Enabled by default | yes (D31) |
| Entity category | none: a main sensor, not diagnostic or configuration |
| Availability | always available while the hive is loaded, like the Brood sensor (D14) |
| Updates | when the hive is set up, and when a break starts or ends (D29) |

## 8. Outdoor temperature

### 8.1 Source

At every sample:

1. If the hive's *Outdoor temperature* setting is set, that entity is used.
2. Otherwise, Met.no's weather entity for the home location: found in the entity registry by
   platform `met` and unique ID `home` (so renaming it doesn't matter), unless it is disabled.
3. Otherwise, if exactly one `weather` entity has a state, that one.
4. Otherwise there is no source: the shared repair is raised ([11.1](#111-no-weather-entity)).

The resolved entity is shown in the sensor's `outdoor_entity` attribute.

### 8.2 Reading and units

| Entity | Value | Unit |
|---|---|---|
| `weather.*` | attribute `temperature` | attribute `temperature_unit` |
| any other domain (temperature sensor) | the state | attribute `unit_of_measurement` |

- State `unavailable` or a missing entity: no value.
- A weather entity whose state (its condition) is `unknown` still gives its temperature.
- The unit must be °C, °F or K, otherwise no value. The value is converted to °C with Home
  Assistant's `TemperatureConverter`.
- A value that isn't a number (for example a sensor state `unknown`), or isn't finite (`nan`,
  `inf`): no value (R30).

### 8.3 Accuracy notes

Met.no gives a forecast for the home coordinates, not a measurement. Home Assistant passes the
home elevation; without it Met.no uses its own coarse terrain model. Met.no is refreshed every
55 to 65 minutes, which is enough for hourly means. Hives far from home should use a local
outdoor sensor.

## 9. Configuration

### 9.1 Hive settings (config entry options)

Shown as **Configure** on the hive in Settings > Devices & services > BroodMinder, only when the
entry's model is 41, 42, 47 or 56. Saving changed settings reloads the hive
(`OptionsFlowWithReload`); the stored hours are kept.

| Key | Label | Type | Values | Default | Effect |
|---|---|---|---|---|---|
| `sensor_position` | Sensor position | required, select (list) | `top_of_frames`: On top of the frames (BroodMinder's standard placement); `in_comb`: In the comb, between frames at brood height | `top_of_frames` | `T_edge` 30 or 32 °C |
| `outdoor_entity` | Outdoor temperature | optional, entity selector | a `sensor` with device class `temperature`, or a `weather` entity | empty | Empty: automatic ([8.1](#81-source)). The selector filters the choice but doesn't check that the entity exists. |

### 9.2 Config entry data

| Key | Set | Value |
|---|---|---|
| `model` | at Bluetooth discovery, from byte 0 of the BroodMinder manufacturer data; for older entries, from the first parsed advertisement | the numeric model id |

The address stays the entry's unique ID. If discovery sees an empty payload, no model is stored
and it is filled in from the first advertisement.

### 9.3 Constants

All tunable values are in [`const.py`](custom_components/broodminder/const.py) and listed in
[6.1](#61-symbols-and-constants) and [7.2](#72-constants), plus:

| Constant | Value | Meaning |
|---|---|---|
| `BROOD_SAMPLE_INTERVAL` | 5 minutes | Sampling interval |
| `BROOD_HISTORY_HOURS` | 48 | Hours kept in memory and storage |
| `BROOD_STORAGE_VERSION` | 2 | Format version of the brood history file, increased with every format change ([12.1](#121-brood-history-file), D30) |
| `OUTDOOR_UNAVAILABLE_ISSUE_AFTER` | 3 hours | How long the outdoor temperature may be missing before the per-hive repair |
| `MET_DOMAIN`, `MET_HOME_UNIQUE_ID` | `met`, `home` | How Met.no's home weather entity is recognised |

## 10. Brood sensor entity

| Property | Value |
|---|---|
| Name | Brood (entity name on the hive's device) |
| Entity ID | `sensor.<device name>_brood`, for example `sensor.broodminder_th_00_00_01_brood` |
| Unique ID | `<bluetooth address>-brood` |
| Device | the hive's device, matched by its Bluetooth connection; created with the same name (`BroodMinder-<model name> <last three octets>`) and model name as the other sensors |
| State | integer percentage 0 to 100, or unknown |
| Unit, state class | `%`, `measurement` (so Home Assistant keeps long-term statistics) |
| Icon | `mdi:hexagon-multiple` |
| Enabled by default | yes |
| Entity category | none: a main sensor, not diagnostic or configuration |
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

## 11. Repairs and logging

Both repairs have severity *warning*, are not fixable from the repair dialog, and are not
persistent: they are not kept across a restart, and are raised again when the condition still
holds. Each logs one warning when it is raised. The texts are in
[`translations/en.json`](custom_components/broodminder/translations/en.json).

### 11.1 No weather entity

- Issue ID: `no_weather_entity`, one for the whole integration.
- Raised when Home Assistant is fully started and at least one loaded hive in automatic mode
  found no outdoor temperature source ([8.1](#81-source)).
- Withdrawn when no such hive remains: a weather entity appears, the hives get a configured
  outdoor entity, or they are unloaded.
- Evaluated at every sample of every hive and whenever a hive stops.
- Text: set the home location and add the Met.no integration, or choose an outdoor temperature in
  each hive's settings; with several weather entities and no Met.no *Forecast Home*, choose one.
- Log: `No weather entity for the brood estimate: add the Met.no integration, or choose an
  outdoor temperature in the settings of each BroodMinder hive`

### 11.2 Outdoor temperature unavailable

- Issue ID: `outdoor_temperature_unavailable_<config entry id>`, one per hive.
- Raised when the hive has an outdoor source and has not read a temperature from it for 3 hours
  or more. The 3 hours are counted from the last successful read, from when the source changed,
  or from when the hive was loaded, whichever is latest.
- Withdrawn at the next successful read, or when the hive unloads.
- Placeholders: `hive` (the device name as the user sees it: their own name for the device, else
  the device name, else the entry title) and `entity_id`.
- Log: `Outdoor temperature <entity> for the brood estimate of <hive> has been unavailable since
  <time>`

## 12. Persistence and resource use

### 12.1 Brood history file

| Property | Value |
|---|---|
| Location | `.storage/broodminder.brood.<config entry id>`, one file per hive |
| Format | Home Assistant `Store`, JSON indented by 2, with the format version in the file (layout and versions below) |
| Size | about 9.2 KB at most (48 hours plus the current one); it doesn't grow |
| Written | when a sample starts a new hour; when the hive unloads (reload, settings change, removal); at Home Assistant's final write when it stops (D15) |
| Read | when the hive is set up |
| Deleted | when the hive is removed |
| Write volume | about 24 writes a day per hive, plus one per restart; about 230 KB a day or 7 MB a month |

The 5-minute samples are never written individually, only the hourly sums.

Layout of version 2 (shortened to one bucket):

```json
{
  "version": 2,
  "minor_version": 1,
  "key": "broodminder.brood.<config entry id>",
  "data": {
    "hours": [
      {"hour": 1793700000, "hive_sum": 413.2, "hive_count": 12, "outdoor_sum": 120.5, "outdoor_count": 12}
    ],
    "brood_break": {"since": null, "low_since": 1793696400, "low_count": 30, "end_count": 0, "last_hour": 1793700000}
  }
}
```

`version` and `minor_version` are written by Home Assistant's `Store`: `version` is
`BROOD_STORAGE_VERSION`, `minor_version` is always 1 (D30). `data` holds `hours`, the buckets
of [5.2](#52-hourly-buckets) sorted by hour, and `brood_break`, the state of [7.3](#73-state).

| Version | Written by | `data` |
|---|---|---|
| 1 | development builds of 0.5.0 | a plain list of buckets |
| 2 | 0.5.0 | an object with `hours` and `brood_break` (D27) |

Every change of the format adds a version to this table, with a migration step from the previous
one after the existing steps (R26, D30, D33). The tests migrate a file of every older version in
this table to the current one, not just the previous version, so a skipped release is covered
(R29). When the hive is set up, the file is used as follows:

| File | Result |
|---|---|
| missing (a new hive) | empty brood history |
| the code's version | used |
| an older version | migrated version by version to the code's version, through every version in between, also those whose releases were never installed (R29, D33), and written back at once (Home Assistant's `Store` does this after a migration). Version 1 becomes `hours`, with an empty `brood_break` (R24). |
| a newer version, or another `minor_version` (a downgrade) | not used: clean brood history and a warning logged. The next save, at the first sample, replaces the file by a clean one in the code's version (R26). Home Assistant 2026.3 and later refuse a newer major version before the migration; that is handled the same way (D35). |
| invalid JSON | Home Assistant's `Store` renames it to `<file>.corrupt.<time>`, logs an error and raises its own repair; clean brood history (R25) |
| unexpected content (missing or wrong fields, or a value of the wrong type such as text or `null` for a number), or a migration that fails | clean brood history and a warning logged; replaced at the next save, at the first sample (R25, R31, D28, D34) |

Log texts:

- `Brood history of <hive> has storage version <version>, newer than this version of the
  integration supports (<BROOD_STORAGE_VERSION>.1); starting with an empty brood history`, where
  `<version>` is the major version alone when it is newer (e.g. `3`), and `<major>.<minor>`
  for another minor version (e.g. `2.2`) (D35)
- `Brood history of <hive> could not be read (<error>); starting with an empty brood history`

`<hive>` is the device name as in [11.2](#112-outdoor-temperature-unavailable). The first
sample starts a new hour, because the brood history is empty, so the save comes at once when
Home Assistant is running, or when it has started (D12).

Version 1 was 8.3 KB. Of the 0.9 KB more in version 2, about 0.2 KB is the break state; the rest
is the two spaces of indentation each line of the hours gets inside the object (measured with 49
buckets).

### 12.2 Other storage

| Data | Where | Written |
|---|---|---|
| Settings and model | `.storage/core.config_entries` | when settings are saved; once when the model is stored |
| Repairs | `.storage/repairs.issue_registry` | when a repair appears or disappears |
| Brood state and attributes | recorder database | when the value or an attribute changes, about once an hour; unchanged updates only refresh the existing row's last-reported time |
| Statistics | recorder database | Brood only: 5-minute statistics and hourly long-term statistics, because the state class is `measurement` |
| Likely brood break since state | recorder database | when a break starts or ends (D29), a few rows a year |
| Entities | `.storage/core.entity_registry` | once when an entity is created, about 1 KB each (measured) |

Rough recorder estimates per hive, not measured: Brood states about 10 KB a day, purged after the
recorder's retention (10 days by default), so about 100 KB steady; 5-minute statistics about
30 KB a day, also purged, about 300 KB steady; hourly statistics about 2 to 3 KB a day, kept
forever, about 1 MB a year. Likely brood break since: under 1 KB, and no statistics.

### 12.3 Memory

About 15 KB per hive for the buckets (measured), constant over time, plus a few hundred bytes
for the likely brood break.

### 12.4 Compatibility between versions

The config entry stays at version 1, so no version needs a config entry migration. What
changing versions does to the brood history and the entities:

| Change | Result |
|---|---|
| Development build of 0.5.0 → 0.5.0 | The version 1 file is migrated: hours kept, no likely brood break, counts start at 0 (R24). |
| 0.5.0 → 0.4.0 or earlier | Those versions don't read the brood file; it stays as it is. Home Assistant shows the Brood and Likely brood break since sensors as no longer provided by the integration; their history and the Brood statistics stay in the recorder. **Configure** disappears, the settings and the stored model stay in the config entry, and the brood repairs go (they aren't persistent). Removing a hive leaves its brood file behind. |
| 0.4.0 or earlier → 0.5.0 again | Entities and settings return. If the other version ran for more than about 6 hours, Brood shows unknown for about 18 hours; hours older than 48 hours are dropped. A likely brood break that had started is kept and ends the normal way. A count in progress continues if the other version ran for less than a day, and otherwise starts over (R22, D26). |
| 0.5.0 → a development build that writes version 1 | That build can't read version 2 and predates R25: the hive fails to set up, with all its sensors. Install 0.5.0 again, or remove `.storage/broodminder.brood.<config entry id>`. |
| Any older version → a later one, skipping releases in between | The file is migrated through the formats of the skipped releases in one go: hours and likely brood break kept, as if each release had been installed in turn (R29, D33). |
| A later version with a newer format → 0.5.0 | Detected by the version in the file: the hive sets up with a clean brood history, logs a warning and replaces the newer file (R26). On every supported Home Assistant version, also 2026.3 and later, which check the version before the migration (D35). |

### 12.5 Backup and restore

A Home Assistant backup (the `backup` integration, or Supervisor on Home Assistant OS) archives
the whole configuration directory. It leaves out only logs, `tts/`, `__pycache__`, earlier
backups and, when the backup is made without it, the database (`EXCLUDE_FROM_BACKUP` and
`EXCLUDE_DATABASE_FROM_BACKUP` in `homeassistant/components/backup/const.py`). The data of the
brood estimate in a backup (R27):

| Data | File | In a backup |
|---|---|---|
| Brood history: hours and likely brood break | `.storage/broodminder.brood.<config entry id>` | always |
| Settings and model | `.storage/core.config_entries` | always |
| Devices and entities (names, entity IDs, disabled) | `.storage/core.device_registry`, `.storage/core.entity_registry` | always |
| The integration, in the version that wrote the brood history | `custom_components/broodminder/` | always |
| History of Brood and Likely brood break since, Brood statistics | `home-assistant_v2.db` | only in a backup with the database; the estimate doesn't need them (D10) |

The rest of the tracker's state isn't stored and needs no backup: the estimate is computed from
the stored hours at setup (D16), the hive temperature comes with the next advertisement, and the
repairs aren't persistent and are raised again by the samples.

The backup holds the brood history file of the last hourly save (D32). Home Assistant's `Store`
writes to a temporary file and renames it into place (`write_utf8_file`), so a backup made during
a save holds the old or the new file, never part of one.

A restore that includes Home Assistant (`restore_homeassistant`) replaces the configuration
directory by the backup's before Home Assistant starts (`homeassistant/backup_restore.py`). That
also replaces the brood history file Home Assistant wrote when it stopped for the restore (D15).
A restore of only the database leaves the brood history file as it is. After the restore, each
hive sets up as after a restart with the backup's brood history (R28). This also holds on
another machine, for example when moving to new hardware: the config entry IDs come from the
backup, and the hives are recognised by their Bluetooth address.

| Age of the backup at the restore | Brood | Likely brood break since |
|---|---|---|
| Up to about 6 hours | An estimate at once from the backup's hours still in the window (at least 18); `hours_used` is lower until new hours fill the window | As in the backup. The estimate at setup comes less than 42 hours after the backup's last one, so counts in progress continue (R22). |
| About 6 to 24 hours | Unknown with `not_enough_data` for about 18 hours: the backup's hours leave the window as fast as new hours arrive | As in the backup. The first estimate, once 18 new hours have arrived, comes at most 42 hours after the backup's last one, so counts in progress continue (R22). |
| Older | Unknown with `not_enough_data` for about 18 hours, as above | A break that had started is kept and ends the normal way (R19). The first estimate comes more than 42 hours after the backup's last one, so a count in progress starts over (R22, D26). |

A backup made before a hive was added doesn't contain it: the hive is discovered again as a new
hive, with an empty brood history. A backup made with 0.4.0 or earlier restores that version,
without a brood estimate; installing 0.5.0 again is described in
[12.4](#124-compatibility-between-versions).

## 13. Lifecycle

| Event | Behaviour |
|---|---|
| Discovery of a new device | Entry created with `model`. For T/TH: tracker started, Brood sensor created right away (unknown, `not_enough_data` or `no_outdoor_temperature`), Likely brood break since created unknown. |
| Setup of an existing T/TH entry | Stored buckets and likely brood break loaded, and the estimate computed from them, so it is available immediately if the stored hours suffice, also while Home Assistant is starting; an estimate already counted for the break is skipped (R23). First sample when Home Assistant has started, or right away if it is running. |
| Setup with a version 1 brood file | Migrated, keeping the hours (R24). |
| Setup with a newer or unreadable brood file | Starts with a clean brood history and logs a warning, and the file is replaced; the hive's other sensors work as usual (R25, R26). |
| Entry without `model` (created before 0.5.0) | No Brood sensor, no Likely brood break since and no settings at first. The first parsed advertisement stores the model; for T/TH the hive reloads once and gets them. |
| Settings saved with changes | Hive reloads with the new settings; buckets and likely brood break kept, the new position's thresholds apply from the next estimate. Saving without changes doesn't reload. |
| Unload | Sampling stops, buckets and likely brood break saved, the hive's unavailable repair withdrawn, the shared repair re-evaluated. |
| Removal | Unload, then the history file, with the likely brood break, is deleted. |
| Home Assistant restart | All buckets, including the hour in progress, and the likely brood break written at the final write; repairs not kept; the per-hive repair can only reappear after 3 hours. |
| Crash or power loss | At most the hour in progress is lost. The likely brood break was stored at the start of that hour, with the hour's estimate already counted ([5.1](#51-sampling)). |
| Home Assistant backup | The brood history file of the last hourly save is in it, with the settings and the integration (R27, D32). |
| Restore of a backup | Home Assistant restarts with the backup's files; each hive sets up with the backup's brood history, as if Home Assistant had been off since the backup (R28, [12.5](#125-backup-and-restore)). |

## 14. Calibration

The constants are starting values chosen from the literature and checked with the synthetic
scenarios in [6.8](#68-reference-values); they have not been fitted to real hives. BroodMinder's
own brood level wasn't available for comparison (the Bees app showed "no computed data").

Plan:

1. Record at each inspection: date, number of frames with brood per box, and for an in-comb
   sensor whether the combs on either side of it have brood.
2. Export the hive and outdoor temperature history from Home Assistant (History > download data).
3. Replay the export through `estimate_brood()` and compare with the inspection notes.
4. Tune, in order of expected impact: `COLONY_WARMING_C`, `BROOD_EDGE_TEMP_C`,
   `STABLE_SWING_RATIO`, `MIN_OUTDOOR_SWING_C`. Update the reference table
   in [6.8](#68-reference-values) and keep the range tests passing.
5. Then the likely brood break: note at inspections and treatments whether there was capped
   brood, and the dates of events that stop laying (swarm, split, caged or lost queen). Replay
   the tuned Brood % through the break rule ([7.4](#74-rule)) and tune `BROOD_BREAK_LOW_PERCENT`
   and `BROOD_BREAK_END_PERCENT` per position, then `BROOD_BREAK_START_HOURS`. Update the table in
   [7.6](#76-how-the-reference-scenarios-count).

In temperate climates the low end (broodless, about 0%) can be checked in winter; the high end
needs the spring build-up. The winter break is also the first chance to see a likely brood break
start and end in a real hive.

## 15. Verification

### 15.1 Automated tests

Run with `scripts/test`, which runs every test against both the oldest supported Home
Assistant (2025.9, the `homeassistant` version in `hacs.json`) and the newest one the test
plugin supports; `scripts/lint` must be clean.

| Requirement | Tests |
|---|---|
| R1 | `test_GIVEN_t_and_scale_WHEN_discovered_THEN_only_t_gets_brood_sensor_and_settings`, `test_GIVEN_only_a_scale_WHEN_no_weather_entity_THEN_no_repair` |
| R2, R11, algorithm ([6](#6-algorithm)) | `test_GIVEN_day_on_top_of_frames_WHEN_estimate_THEN_brood_in_expected_range`, `test_GIVEN_brood_around_comb_sensor_WHEN_estimate_THEN_brood_high`, `test_GIVEN_brood_break_at_comb_sensor_WHEN_estimate_THEN_in_comb_reads_low`, `test_GIVEN_steady_day_WHEN_estimate_THEN_level_is_share_of_way_to_brood_temperature`, `test_GIVEN_cool_and_warm_hours_WHEN_estimate_THEN_hours_weigh_by_their_span`, `test_GIVEN_hive_swinging_half_of_outdoors_WHEN_estimate_THEN_stability_reduced`, `test_GIVEN_every_hour_too_hot_WHEN_estimate_THEN_too_hot` |
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

Likely brood break and the brood history file:

| Requirement | Tests |
|---|---|
| R16, D31 | `test_GIVEN_t_and_scale_WHEN_discovered_THEN_only_t_gets_brood_sensor_and_settings` (also Likely brood break since, enabled by default) |
| R17, R18, R21, rule ([7.4](#74-rule)) | `test_GIVEN_48_low_estimates_WHEN_break_rule_THEN_break_since_first_low_estimate`, `test_GIVEN_47_low_estimates_WHEN_break_rule_THEN_no_break`, `test_GIVEN_estimate_above_low_WHEN_counting_low_THEN_count_starts_over`, `test_GIVEN_47_low_estimates_WHEN_next_hour_completes_low_THEN_break_shown` |
| R19, D24 | `test_GIVEN_break_WHEN_24_estimates_above_end_level_THEN_break_ends`, `test_GIVEN_break_WHEN_estimates_between_low_and_end_level_THEN_break_continues` |
| R20, D22, [7.6](#76-how-the-reference-scenarios-count) | `test_GIVEN_reference_scenarios_WHEN_break_thresholds_THEN_count_as_specified`, `test_GIVEN_in_comb_position_WHEN_break_rule_THEN_its_thresholds_apply` |
| R22, D26 | `test_GIVEN_gap_of_42_hours_WHEN_counting_THEN_count_continues`, `test_GIVEN_gap_over_42_hours_WHEN_counting_THEN_count_starts_over_and_break_kept`, `test_GIVEN_outage_under_a_day_WHEN_estimates_return_THEN_count_continues`, `test_GIVEN_outage_of_a_day_WHEN_estimates_return_THEN_count_starts_over` (Home Assistant off and running) |
| R23 | `test_GIVEN_estimate_already_counted_WHEN_break_rule_THEN_skipped`, `test_GIVEN_47_low_estimates_stored_WHEN_hive_set_up_THEN_break_shown_and_kept_on_reload` |
| R24, R26, R29, D27, D33 | `test_GIVEN_version_1_brood_history_WHEN_hive_set_up_THEN_hours_migrated`, `test_GIVEN_hive_sampling_WHEN_hour_completes_THEN_hours_stored_without_unload` (version 2; version 1 is the only older version so far) |
| R25, D28 | `test_GIVEN_unreadable_brood_history_WHEN_set_up_THEN_sensors_work_and_warning_logged` (wrong fields, no `brood_break`, not an object) |
| R30 | `test_GIVEN_outdoor_state_WHEN_read_THEN_temperature_in_celsius` (sensor `nan` and `inf`, weather `nan`) |
| R31, D34 | `test_GIVEN_unreadable_brood_history_WHEN_set_up_THEN_sensors_work_and_warning_logged` (`null` sum, text `since`, `true` count), `test_GIVEN_brood_history_with_whole_number_sums_WHEN_set_up_THEN_hours_used` |
| R26, D30, D35 | `test_GIVEN_newer_brood_history_version_WHEN_set_up_THEN_clean_file_and_warning_logged` (newer version, other `minor_version`; D35 by the run against the latest Home Assistant) |
| D29 | `test_GIVEN_no_break_change_WHEN_samples_THEN_break_state_not_written` |
| R28, D32 | `test_GIVEN_backup_4_hours_old_WHEN_restored_THEN_estimate_at_once_and_count_continues`, `test_GIVEN_backup_20_hours_old_WHEN_restored_THEN_count_continues_once_window_refills`, `test_GIVEN_backup_2_days_old_WHEN_restored_THEN_break_kept_and_count_starts_over` (a brood history file as of a backup, with the hour in progress at its first sample) |

Not covered by automated tests: N1 to N4 (by review), the startup guard of the shared repair
(D12), a brood history file with invalid JSON (handled by Home Assistant's `Store`, which the
test storage bypasses), and real Bluetooth reception. R27 (what a backup contains) is verified by
review against [12.5](#125-backup-and-restore): all stored state is in `.storage/` through
`Store` or the config entry, and nothing outside the configuration directory. A real backup and
restore is a manual check.

### 15.2 Manual checks on real hardware

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
9. A T/TH hive has Likely brood break since, unknown while the Brood % is high; a scale doesn't.
10. After an upgrade from a development build, the Brood value is back right away (the hours
    were migrated).
11. During a real brood break (for example the winter break) it shows a date about 2 to 3 days
    after the Brood % dropped, backdated to the drop, and keeps it across a restart.
12. On a test installation, not the production one: a backup made while the Brood sensor shows
    a value contains `.storage/broodminder.brood.<entry id>`, also without the database.
    Restoring it within a few hours shows the value right away, and keeps Likely brood break
    since.

## 16. Known limitations

- The sensor measures one point; the percentage is relative, not frames of brood, and below
  about 20% it is rough.
- In the comb, the estimate shows whether the brood nest reaches the sensor, not how big it is.
- Hours with an outdoor temperature of 31 °C or more don't count towards the level. In climates
  that stay that warm day and night, the sensor often shows unknown.
- Those hot hours do count towards stability (D18). When a colony with brood can't cool the hive
  in a heatwave and the hive temperature climbs above 35 °C in the afternoon, stability counts
  that as following the weather, so a strong colony can lose some percentage points on such days.
- The estimate lags up to an hour, because only complete hours are used.
- A new hive, or one whose history was lost, needs about 18 hours before the first value.
- After restoring a backup more than about 6 hours old, the Brood sensor shows unknown for about
  18 hours. If the backup is more than a day old, a count in progress towards starting or ending
  a likely brood break also starts over ([12.5](#125-backup-and-restore)). A backup doesn't contain the samples of the hour in progress
  (D32).
- The automatic outdoor temperature is a forecast for the home location; accuracy depends on the
  home elevation, and distant apiaries need a local sensor.
- With several weather entities and no Met.no *Forecast Home*, each hive needs a configured
  outdoor entity.
- The constants are not calibrated yet ([14](#14-calibration)).

Likely brood break:

- It can't tell no brood from brood away from the sensor: a small brood nest far from the
  sensor, a winter cluster that moved, or brood restarting in winter also count as low
  ([7.6](#76-how-the-reference-scenarios-count)). A likely brood break is a reason to check a
  frame for capped brood, not proof that there is none.
- It is late. The Brood % covers the last 24 hours, so it falls up to a day after the brood near
  the sensor has gone, and the break is confirmed 48 estimates later: about 2 to 3 days after the
  drop. The start shown is backdated (D23); the moment the sensor changes is not.
- The end is late too. A small new egg patch may not warm the sensor at once, and the Brood %
  must then stay above the end level for 24 hours. By the time the sensor goes back to unknown,
  the queen may have been laying for several days, and the first new cells are capped about
  8 days after she starts ([2.4](#24-brood-development-and-the-window-without-capped-brood)).
- A laying stop of less than about 3 weeks never leaves the hive without brood, so it never shows
  as a likely brood break, even when there is a short window without capped brood.
- Going back from 0.5.0 to a development build that writes storage version 1 makes the hive fail
  to set up ([12.4](#124-compatibility-between-versions)).

## 17. References

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
- Winston M. L. 1987, The Biology of the Honey Bee, Harvard University Press (brood development
  times)
