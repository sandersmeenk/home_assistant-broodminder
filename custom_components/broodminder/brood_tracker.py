"""Keeps a hive's brood estimate and likely brood break up to date."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.weather import (
    ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_TEMPERATURE_UNIT,
    DOMAIN as WEATHER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_HOMEASSISTANT_FINAL_WRITE,
    STATE_UNAVAILABLE,
    UnitOfTemperature,
)
from homeassistant.core import CALLBACK_TYPE, CoreState, Event, HomeAssistant, State, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey
from homeassistant.util.unit_conversion import TemperatureConverter

from .brood import (
    SECONDS_PER_HOUR,
    BroodBreak,
    BroodEstimate,
    HourlyTemperatures,
    brood_window,
    count_brood_break,
    estimate_brood,
    hour_start,
)
from .const import (
    BROOD_HISTORY_HOURS,
    BROOD_SAMPLE_INTERVAL,
    BROOD_STATUS_NO_OUTDOOR_TEMPERATURE,
    BROOD_STATUS_NOT_ENOUGH_DATA,
    BROOD_STATUS_OK,
    BROOD_STORAGE_VERSION,
    CONF_OUTDOOR_ENTITY,
    CONF_SENSOR_POSITION,
    DEFAULT_SENSOR_POSITION,
    DOMAIN,
    ISSUE_NO_WEATHER_ENTITY,
    ISSUE_OUTDOOR_UNAVAILABLE,
    MET_DOMAIN,
    MET_HOME_UNIQUE_ID,
    OUTDOOR_UNAVAILABLE_ISSUE_AFTER,
)

_LOGGER = logging.getLogger(__name__)

# Running brood trackers: the missing weather entity repair is shared by all hives
BROOD_TRACKERS: HassKey[set[BroodTracker]] = HassKey(f"{DOMAIN}_brood_trackers")


def outdoor_temperature_c(state: State | None) -> float | None:
    """Return the temperature of a temperature sensor or weather entity in °C."""
    if state is None or state.state == STATE_UNAVAILABLE:
        return None

    if state.domain == WEATHER_DOMAIN:
        # A weather entity's state is its condition, which may be unknown
        value = state.attributes.get(ATTR_WEATHER_TEMPERATURE)
        unit = state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT)
    else:
        value = state.state
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

    if unit not in TemperatureConverter.VALID_UNITS:
        return None
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        return None
    return TemperatureConverter.convert(temperature, unit, UnitOfTemperature.CELSIUS)


@callback
def async_find_weather_entity(hass: HomeAssistant) -> str | None:
    """Return Met.no's weather entity for the home location, or else the only weather entity."""
    registry = er.async_get(hass)
    met_home = registry.async_get_entity_id(WEATHER_DOMAIN, MET_DOMAIN, MET_HOME_UNIQUE_ID)
    if met_home is not None and (entry := registry.async_get(met_home)) and not entry.disabled:
        return met_home

    weather_entity_ids = hass.states.async_entity_ids(WEATHER_DOMAIN)
    return weather_entity_ids[0] if len(weather_entity_ids) == 1 else None


async def async_remove_brood_history(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the stored hours of a hive that is removed."""
    await Store(hass, BROOD_STORAGE_VERSION, _storage_key(entry)).async_remove()


def _storage_key(entry: ConfigEntry) -> str:
    return f"{DOMAIN}.brood.{entry.entry_id}"


class UnsupportedBroodHistoryError(Exception):
    """The brood history file has a storage version this code doesn't know."""

    def __init__(self, major_version: int, minor_version: int) -> None:
        """Initialize with the file's storage version."""
        self.version = f"{major_version}.{minor_version}"
        super().__init__(self.version)


class BroodHistoryStore(Store[dict[str, Any]]):
    """The brood history file of a hive: older storage versions are migrated."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: Any
    ) -> dict[str, Any]:
        """Migrate an older file; a newer one is left by a downgrade and can't be read."""
        # Only the major version changes with the format, so another minor version is newer
        if old_major_version > BROOD_STORAGE_VERSION or old_minor_version != 1:
            raise UnsupportedBroodHistoryError(old_major_version, old_minor_version)
        if old_major_version == 1:
            # Development builds of 0.5.0 stored only the hours
            old_data = {"hours": old_data, "brood_break": asdict(BroodBreak())}
        return old_data


@callback
def _async_update_no_weather_issue(hass: HomeAssistant) -> None:
    """Raise the repair while a hive finds no weather entity, and withdraw it otherwise."""
    # Before Home Assistant has started, other integrations' weather entities may not exist yet
    missing = hass.state is CoreState.running and any(
        tracker.automatic and tracker.outdoor_entity_id is None
        for tracker in hass.data.get(BROOD_TRACKERS, set())
    )
    if not missing:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_NO_WEATHER_ENTITY)
        return

    if ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_NO_WEATHER_ENTITY) is None:
        _LOGGER.warning(
            "No weather entity for the brood estimate: add the Met.no integration, or choose "
            "an outdoor temperature in the settings of each BroodMinder hive"
        )
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_NO_WEATHER_ENTITY,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_NO_WEATHER_ENTITY,
    )


class BroodTracker:
    """Samples a hive's temperature and the outdoor temperature, and estimates brood."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, hive_available: Callable[[], bool]
    ) -> None:
        """Initialize the tracker; hive_available tells whether the hive is still in range."""
        self.hass = hass
        self.entry = entry
        self.position: str = entry.options.get(CONF_SENSOR_POSITION, DEFAULT_SENSOR_POSITION)
        self.outdoor_entity_id: str | None = None
        self.estimate = BroodEstimate(BROOD_STATUS_NOT_ENOUGH_DATA)
        self.brood_break = BroodBreak()
        self._configured_outdoor_entity_id: str | None = entry.options.get(CONF_OUTDOOR_ENTITY)
        self._hive_available = hive_available
        self._hive_c: float | None = None
        self._outdoor_missing = False  # the latest sample had no outdoor temperature
        self._outdoor_read_at = dt_util.utcnow()
        self._hours: dict[int, HourlyTemperatures] = {}
        self._store = BroodHistoryStore(hass, BROOD_STORAGE_VERSION, _storage_key(entry))
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribes: list[CALLBACK_TYPE] = []

    @property
    def automatic(self) -> bool:
        """Return whether the outdoor temperature comes from Home Assistant's weather."""
        return self._configured_outdoor_entity_id is None

    @property
    def status(self) -> str:
        """Return why there is no estimate, or ok."""
        if self.estimate.status != BROOD_STATUS_OK and self._outdoor_missing:
            return BROOD_STATUS_NO_OUTDOOR_TEMPERATURE
        return self.estimate.status

    @property
    def _unavailable_issue_id(self) -> str:
        return f"{ISSUE_OUTDOOR_UNAVAILABLE}_{self.entry.entry_id}"

    async def async_start(self) -> None:
        """Load the stored hours and brood break, and start sampling."""
        # A file that can't be used must not keep the hive's other sensors from working; the
        # next save replaces it
        try:
            self._load(await self._store.async_load())
        except UnsupportedBroodHistoryError as err:
            _LOGGER.warning(
                "Brood history of %s has storage version %s, newer than this version of the "
                "integration supports (%s.1); starting with an empty brood history",
                self._hive_name(),
                err.version,
                BROOD_STORAGE_VERSION,
            )
        except (KeyError, TypeError) as err:
            _LOGGER.warning(
                "Brood history of %s could not be read (%r); starting with an empty brood "
                "history",
                self._hive_name(),
                err,
            )
        # The stored hours may already give an estimate before the first sample
        self._async_update_estimate(hour_start(dt_util.utcnow().timestamp()))
        self.hass.data.setdefault(BROOD_TRACKERS, set()).add(self)
        self._unsubscribes.append(
            async_track_time_interval(self.hass, self._async_sample, BROOD_SAMPLE_INTERVAL)
        )
        # Home Assistant doesn't unload its config entries when it stops
        self._unsubscribes.append(
            self.hass.bus.async_listen(EVENT_HOMEASSISTANT_FINAL_WRITE, self._async_save)
        )
        # Weather entities may only appear once Home Assistant has started
        self._unsubscribes.append(async_at_started(self.hass, self._async_started))

    async def async_stop(self) -> None:
        """Stop sampling, save the hours and withdraw this hive's repairs."""
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()
        self.hass.data[BROOD_TRACKERS].discard(self)
        ir.async_delete_issue(self.hass, DOMAIN, self._unavailable_issue_id)
        _async_update_no_weather_issue(self.hass)
        await self._store.async_save(self._stored_data())

    @callback
    def async_set_hive_temperature(self, temperature_c: float | None) -> None:
        """Remember the hive temperature of the latest advertisement."""
        self._hive_c = temperature_c

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Call update_callback after every sample; returns a function to stop."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        return remove_listener

    async def _async_save(self, _event: Event) -> None:
        """Store the hours, including the hour in progress, when Home Assistant stops."""
        await self._store.async_save(self._stored_data())

    @callback
    def _async_started(self, hass: HomeAssistant) -> None:
        self._async_sample(dt_util.utcnow())

    @callback
    def _async_sample(self, now: datetime) -> None:
        """Add a sample to the current hour, update the estimate and the repairs."""
        outdoor_entity_id = self._configured_outdoor_entity_id or async_find_weather_entity(
            self.hass
        )
        if outdoor_entity_id != self.outdoor_entity_id:
            self.outdoor_entity_id = outdoor_entity_id
            self._outdoor_read_at = now  # a new source gets time to report
        outdoor_c = (
            outdoor_temperature_c(self.hass.states.get(outdoor_entity_id))
            if outdoor_entity_id
            else None
        )
        self._outdoor_missing = outdoor_c is None
        if outdoor_c is not None:
            self._outdoor_read_at = now
        # The last advertisement only counts while the hive is still in range
        hive_c = self._hive_c if self._hive_available() else None

        current_hour = hour_start(now.timestamp())
        hour_completed = current_hour not in self._hours
        self._hours.setdefault(current_hour, HourlyTemperatures(current_hour)).add(
            hive_c, outdoor_c
        )
        oldest_hour = current_hour - BROOD_HISTORY_HOURS * SECONDS_PER_HOUR
        self._hours = {hour: t for hour, t in self._hours.items() if hour >= oldest_hour}
        if hour_completed:
            # Store once an hour, so a crash loses at most the hour in progress. The data is
            # taken when it's written, after this sample, so it has the hour's brood break.
            self._store.async_delay_save(self._stored_data)

        self._async_update_estimate(current_hour)
        self._async_update_unavailable_issue(now)
        _async_update_no_weather_issue(self.hass)
        for update_callback in self._listeners:
            update_callback()

    @callback
    def _async_update_estimate(self, current_hour: int) -> None:
        """Estimate brood from the complete hours before current_hour, and count it."""
        self.estimate = estimate_brood(
            brood_window(list(self._hours.values()), current_hour), self.position
        )
        if self.estimate.brood_percent is not None:
            self.brood_break = count_brood_break(
                self.brood_break, current_hour, self.estimate.brood_percent, self.position
            )

    @callback
    def _async_update_unavailable_issue(self, now: datetime) -> None:
        """Raise the repair when the outdoor temperature has been unavailable for long."""
        if (
            self.outdoor_entity_id is None
            or now - self._outdoor_read_at < OUTDOOR_UNAVAILABLE_ISSUE_AFTER
        ):
            ir.async_delete_issue(self.hass, DOMAIN, self._unavailable_issue_id)
            return

        hive = self._hive_name()
        if ir.async_get(self.hass).async_get_issue(DOMAIN, self._unavailable_issue_id) is None:
            _LOGGER.warning(
                "Outdoor temperature %s for the brood estimate of %s "
                "has been unavailable since %s",
                self.outdoor_entity_id,
                hive,
                self._outdoor_read_at,
            )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._unavailable_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_OUTDOOR_UNAVAILABLE,
            translation_placeholders={"hive": hive, "entity_id": self.outdoor_entity_id},
        )

    def _hive_name(self) -> str:
        """Return the hive's device name as the user sees it."""
        device = dr.async_get(self.hass).async_get_device(
            connections={(dr.CONNECTION_BLUETOOTH, self.entry.unique_id or "")}
        )
        if device is None:
            return self.entry.title
        return device.name_by_user or device.name or self.entry.title

    def _load(self, stored: dict[str, Any] | None) -> None:
        """Take the hours and brood break from stored data, or keep them empty."""
        if stored is None:
            return
        hours = {data["hour"]: HourlyTemperatures(**data) for data in stored["hours"]}
        self.brood_break = BroodBreak(**stored["brood_break"])
        self._hours = hours

    def _stored_data(self) -> dict[str, Any]:
        return {
            "hours": [
                asdict(hours) for hours in sorted(self._hours.values(), key=lambda h: h.hour)
            ],
            "brood_break": asdict(self.brood_break),
        }
