"""Tests for broodminder/brood.py."""
# ruff: noqa: PLR2004

from collections.abc import Callable
import math

from homeassistant.core import State
import pytest

from custom_components.broodminder.brood import (
    BroodEstimate,
    HourlyTemperatures,
    brood_window,
    estimate_brood,
    hour_start,
)
from custom_components.broodminder.brood_tracker import outdoor_temperature_c
from custom_components.broodminder.const import (
    BROOD_STATUS_NOT_ENOUGH_DATA,
    BROOD_STATUS_OK,
    BROOD_STATUS_TOO_HOT,
    POSITION_IN_COMB,
    POSITION_TOP_OF_FRAMES,
)

HOUR = 3600


def _day(
    outdoor_min: float, outdoor_max: float, hive: Callable[[float, int], float]
) -> list[tuple[float, float]]:
    """Return 24 hourly (hive, outdoor) temperatures: coldest at 4:00, warmest at 16:00.

    hive(outdoor, hour) returns the hive temperature of that hour.
    """
    hours = []
    for hour in range(24):
        middle = (outdoor_min + outdoor_max) / 2
        amplitude = (outdoor_max - outdoor_min) / 2
        outdoor = middle - amplitude * math.cos(2 * math.pi * (hour - 4) / 24)
        hours.append((hive(outdoor, hour), outdoor))
    return hours


def _estimate(hours: list[tuple[float, float]], position: str) -> int:
    estimate = estimate_brood(hours, position)
    assert estimate.status == BROOD_STATUS_OK
    assert estimate.brood_percent is not None
    return estimate.brood_percent


@pytest.mark.parametrize(
    ("hours", "minimum", "maximum"),
    [
        # Full brood: held at 35 °C on a mild day
        (_day(12, 25, lambda _, h: 35.0 + 0.3 * math.sin(h)), 90, 100),
        # Partial brood: a little below 35 °C, barely following the weather
        (_day(12, 25, lambda o, _: 33.5 + 0.12 * (o - 18.5)), 40, 90),
        # Small brood nest far from the sensor: well below 35 °C, following the weather
        (_day(12, 25, lambda o, _: 31.0 + 0.35 * (o - 18.5)), 5, 40),
        # No brood: the hive follows the weather, a few degrees warmer
        (_day(12, 25, lambda o, _: o + 6), 0, 5),
        # No brood in a heatwave: the weather alone brings the hive near 35 °C
        (_day(24, 38, lambda o, _: min(o + 3, 36)), 0, 5),
        # Full brood in a heatwave: the colony cools the hive to 35 °C
        (_day(24, 38, lambda o, _: 35.2 + 0.05 * (o - 31)), 90, 100),
        # Winter cluster without brood: far above outdoors, far below brood temperature
        (_day(-2, 6, lambda o, _: 18 + 0.3 * o), 0, 5),
        # Winter, brood rearing restarts near the sensor
        (_day(-2, 6, lambda o, _: 31 + 0.2 * o), 10, 50),
    ],
    ids=[
        "full_brood",
        "partial_brood",
        "small_brood",
        "no_brood",
        "no_brood_heatwave",
        "full_brood_heatwave",
        "winter_cluster",
        "winter_brood_restarts",
    ],
)
def test_GIVEN_day_on_top_of_frames_WHEN_estimate_THEN_brood_in_expected_range(
    hours: list[tuple[float, float]], minimum: int, maximum: int
) -> None:
    """Verifies typical hive days on top of the frames give a plausible brood percentage."""
    assert minimum <= _estimate(hours, POSITION_TOP_OF_FRAMES) <= maximum


def test_GIVEN_brood_around_comb_sensor_WHEN_estimate_THEN_brood_high() -> None:
    """Verifies a sensor in the comb surrounded by brood reads nearly full brood."""
    hours = _day(12, 25, lambda _, h: 34.8 + 0.2 * math.sin(h))

    assert _estimate(hours, POSITION_IN_COMB) >= 90


def test_GIVEN_brood_break_at_comb_sensor_WHEN_estimate_THEN_in_comb_reads_low() -> None:
    """Verifies the in-comb lower bound doesn't count a warm broodless comb as brood."""
    hours = _day(15, 27, lambda o, _: 31.5 + 0.25 * (o - 21))

    in_comb = _estimate(hours, POSITION_IN_COMB)

    assert in_comb <= 10
    assert in_comb < _estimate(hours, POSITION_TOP_OF_FRAMES)


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        # Reference max(20 + 4, 30) = 30: (33.5 - 30) / (35 - 30) = 0.7
        (POSITION_TOP_OF_FRAMES, 70),
        # Reference max(20 + 4, 32) = 32: (33.5 - 32) / (35 - 32) = 0.5
        (POSITION_IN_COMB, 50),
    ],
)
def test_GIVEN_steady_day_WHEN_estimate_THEN_level_is_share_of_way_to_brood_temperature(
    position: str, expected: int
) -> None:
    """Verifies the hourly score: how far the hive is from its reference towards 35 °C."""
    hours = [(33.5, 20.0)] * 24

    estimate = estimate_brood(hours, position)

    assert estimate.brood_percent == expected
    assert estimate.stability == 1.0  # no outdoor swing: stability is skipped


def test_GIVEN_hive_swinging_half_of_outdoors_WHEN_estimate_THEN_stability_reduced() -> None:
    """Verifies stability: half the outdoor swing is (1 - 0.5) / (1 - 0.2) = 0.625."""
    hours = _day(10, 20, lambda o, _: 25 + 0.5 * (o - 15))

    estimate = estimate_brood(hours, POSITION_TOP_OF_FRAMES)

    assert estimate.stability == pytest.approx(0.625)


def test_GIVEN_too_few_hours_WHEN_estimate_THEN_not_enough_data() -> None:
    """Verifies the estimate needs 18 hours with both temperatures."""
    assert estimate_brood([(35.0, 20.0)] * 17, POSITION_TOP_OF_FRAMES) == BroodEstimate(
        BROOD_STATUS_NOT_ENOUGH_DATA, hours_used=17
    )
    assert estimate_brood([(35.0, 20.0)] * 18, POSITION_TOP_OF_FRAMES).status == BROOD_STATUS_OK


def test_GIVEN_every_hour_too_hot_WHEN_estimate_THEN_too_hot() -> None:
    """Verifies a day hot enough to explain brood temperature gives no estimate."""
    estimate = estimate_brood([(35.0, 32.0)] * 24, POSITION_TOP_OF_FRAMES)

    assert estimate == BroodEstimate(BROOD_STATUS_TOO_HOT, hours_used=24)


def test_GIVEN_samples_WHEN_added_to_hour_THEN_means_skip_missing_temperatures() -> None:
    """Verifies an hour averages its samples and skips missing ones per temperature."""
    hour = HourlyTemperatures(hour=0)
    hour.add(34.0, None)
    hour.add(36.0, 10.0)
    hour.add(None, 14.0)

    assert hour.hive_c == 35.0
    assert hour.outdoor_c == 12.0
    assert HourlyTemperatures(hour=0).hive_c is None


def test_GIVEN_timestamp_WHEN_hour_start_THEN_rounded_down_to_hour() -> None:
    """Verifies samples are grouped by the hour they fall in."""
    assert hour_start(100 * HOUR + 1234.5) == 100 * HOUR


def test_GIVEN_stored_hours_WHEN_brood_window_THEN_last_24_complete_hours_with_both() -> None:
    """Verifies the window skips old hours, the current hour and hours missing a temperature."""
    current = 1000 * HOUR

    def hour(offset: int, hive_c: float | None, outdoor_c: float | None) -> HourlyTemperatures:
        temperatures = HourlyTemperatures(hour=current + offset * HOUR)
        temperatures.add(hive_c, outdoor_c)
        return temperatures

    hours = [
        hour(0, 30.0, 10.0),  # current hour: not complete yet
        hour(-1, 35.0, 15.0),
        hour(-2, 34.0, None),  # no outdoor temperature
        hour(-24, 33.0, 14.0),  # oldest hour in the window
        hour(-25, 32.0, 13.0),  # too old
    ]

    assert brood_window(hours, current) == [(33.0, 14.0), (35.0, 15.0)]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (State("sensor.outdoor", "20.5", {"unit_of_measurement": "°C"}), 20.5),
        (State("sensor.outdoor", "68", {"unit_of_measurement": "°F"}), 20.0),
        # A weather entity's state is its condition: the temperature is an attribute
        (State("weather.home", "sunny", {"temperature": 68, "temperature_unit": "°F"}), 20.0),
        (State("weather.home", "unknown", {"temperature": 20, "temperature_unit": "°C"}), 20.0),
        (State("weather.home", "unavailable", {}), None),
        (State("sensor.outdoor", "unavailable", {"unit_of_measurement": "°C"}), None),
        (State("sensor.outdoor", "unknown", {"unit_of_measurement": "°C"}), None),
        # Without a temperature unit the value can't be trusted to be a temperature
        (State("sensor.outdoor", "20", {}), None),
        (None, None),
    ],
    ids=[
        "sensor_celsius",
        "sensor_fahrenheit",
        "weather_fahrenheit",
        "weather_unknown_condition",
        "weather_unavailable",
        "sensor_unavailable",
        "sensor_unknown",
        "sensor_without_unit",
        "missing",
    ],
)
def test_GIVEN_outdoor_state_WHEN_read_THEN_temperature_in_celsius(
    state: State | None, expected: float | None
) -> None:
    """Verifies the outdoor temperature is read from sensors and weather entities in °C."""
    assert outdoor_temperature_c(state) == pytest.approx(expected)
