"""Tests for broodminder/brood.py."""
# ruff: noqa: PLR2004

from collections.abc import Callable
import math

from homeassistant.core import State
import pytest

from custom_components.broodminder.brood import (
    BroodBreak,
    BroodEstimate,
    HourlyTemperatures,
    brood_window,
    count_brood_break,
    estimate_brood,
    hour_start,
)
from custom_components.broodminder.brood_tracker import outdoor_temperature_c
from custom_components.broodminder.const import (
    BROOD_BREAK_END_PERCENT,
    BROOD_BREAK_LOW_PERCENT,
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


# The reference scenarios of BROOD_ESTIMATE.md 6.8
# Full brood: held at 35 °C on a mild day
FULL_BROOD = _day(12, 25, lambda _, h: 35.0 + 0.3 * math.sin(h))
# Partial brood: a little below 35 °C, barely following the weather
PARTIAL_BROOD = _day(12, 25, lambda o, _: 33.5 + 0.12 * (o - 18.5))
# Small brood nest far from the sensor: well below 35 °C, following the weather
SMALL_BROOD = _day(12, 25, lambda o, _: 31.0 + 0.35 * (o - 18.5))
# No brood: the hive follows the weather, a few degrees warmer
NO_BROOD = _day(12, 25, lambda o, _: o + 6)
# No brood in a heatwave: the weather alone brings the hive near 35 °C
NO_BROOD_HEATWAVE = _day(24, 38, lambda o, _: min(o + 3, 36))
# Full brood in a heatwave: the colony cools the hive to 35 °C
FULL_BROOD_HEATWAVE = _day(24, 38, lambda o, _: 35.2 + 0.05 * (o - 31))
# Winter cluster without brood: far above outdoors, far below brood temperature
WINTER_CLUSTER = _day(-2, 6, lambda o, _: 18 + 0.3 * o)
# Winter, brood rearing restarts near the sensor
WINTER_BROOD_RESTARTS = _day(-2, 6, lambda o, _: 31 + 0.2 * o)
# Brood all around a sensor in the comb
BROOD_AROUND_COMB_SENSOR = _day(12, 25, lambda _, h: 34.8 + 0.2 * math.sin(h))
# Brood break: the bees keep the comb warm, but below the brood range
BROOD_BREAK_BEES_PRESENT = _day(15, 27, lambda o, _: 31.5 + 0.25 * (o - 21))


def _estimate(hours: list[tuple[float, float]], position: str) -> int:
    estimate = estimate_brood(hours, position)
    assert estimate.status == BROOD_STATUS_OK
    assert estimate.brood_percent is not None
    return estimate.brood_percent


@pytest.mark.parametrize(
    ("hours", "minimum", "maximum"),
    [
        (FULL_BROOD, 90, 100),
        (PARTIAL_BROOD, 40, 90),
        (SMALL_BROOD, 5, 40),
        (NO_BROOD, 0, 5),
        (NO_BROOD_HEATWAVE, 0, 5),
        (FULL_BROOD_HEATWAVE, 90, 100),
        (WINTER_CLUSTER, 0, 5),
        (WINTER_BROOD_RESTARTS, 10, 50),
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
    assert _estimate(BROOD_AROUND_COMB_SENSOR, POSITION_IN_COMB) >= 90


def test_GIVEN_brood_break_at_comb_sensor_WHEN_estimate_THEN_in_comb_reads_low() -> None:
    """Verifies the in-comb lower bound doesn't count a warm broodless comb as brood."""
    in_comb = _estimate(BROOD_BREAK_BEES_PRESENT, POSITION_IN_COMB)

    assert in_comb <= 10
    assert in_comb < _estimate(BROOD_BREAK_BEES_PRESENT, POSITION_TOP_OF_FRAMES)


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


def test_GIVEN_cool_and_warm_hours_WHEN_estimate_THEN_hours_weigh_by_their_span() -> None:
    """Verifies a warm hour counts less: by its span, the room left below 35 °C."""
    # 20 °C outdoors: reference 30 °C, span 5, hive at 35 °C scores 1
    # 30 °C outdoors: reference 34 °C, span 1, hive at 34 °C scores 0
    hours = [(35.0, 20.0)] * 12 + [(34.0, 30.0)] * 12

    estimate = estimate_brood(hours, POSITION_TOP_OF_FRAMES)

    assert estimate.level == pytest.approx((5 * 1 + 1 * 0) / (5 + 1))
    assert estimate.stability == 1.0  # hive swing 1 °C is a tenth of the outdoor 10 °C


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
        # "nan" and "inf" parse as floats, but aren't temperatures
        (State("sensor.outdoor", "nan", {"unit_of_measurement": "°C"}), None),
        (State("sensor.outdoor", "inf", {"unit_of_measurement": "°C"}), None),
        (State("weather.home", "sunny", {"temperature": "nan", "temperature_unit": "°C"}), None),
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
        "sensor_nan",
        "sensor_infinite",
        "weather_nan",
        "sensor_without_unit",
        "missing",
    ],
)
def test_GIVEN_outdoor_state_WHEN_read_THEN_temperature_in_celsius(
    state: State | None, expected: float | None
) -> None:
    """Verifies the outdoor temperature is read from sensors and weather entities in °C."""
    assert outdoor_temperature_c(state) == pytest.approx(expected)


START = 1000 * HOUR  # time of the first estimate in the brood break tests


def _count(
    estimates: list[int],
    brood_break: BroodBreak | None = None,
    first_hour: int = START,
    position: str = POSITION_TOP_OF_FRAMES,
) -> BroodBreak:
    """Return the likely brood break after hourly brood estimates from first_hour on."""
    brood_break = brood_break or BroodBreak()
    for offset, brood_percent in enumerate(estimates):
        brood_break = count_brood_break(
            brood_break, first_hour + offset * HOUR, brood_percent, position
        )
    return brood_break


def _counts_as(brood_percent: int, position: str) -> str:
    if brood_percent <= BROOD_BREAK_LOW_PERCENT[position]:
        return "low"
    if brood_percent > BROOD_BREAK_END_PERCENT[position]:
        return "above end"
    return "between"


def test_GIVEN_48_low_estimates_WHEN_break_rule_THEN_break_since_first_low_estimate() -> None:
    """Verifies a break starts after 48 low estimates and is backdated to the first one."""
    brood_break = _count([70] * 5 + [24] + [12] * 47)  # top of frames: low is 30% or less

    assert brood_break == BroodBreak(since=START + 5 * HOUR, last_hour=START + 52 * HOUR)


def test_GIVEN_47_low_estimates_WHEN_break_rule_THEN_no_break() -> None:
    """Verifies 47 low estimates are not yet a break."""
    brood_break = _count([30] * 47)

    assert brood_break == BroodBreak(low_since=START, low_count=47, last_hour=START + 46 * HOUR)


def test_GIVEN_estimate_above_low_WHEN_counting_low_THEN_count_starts_over() -> None:
    """Verifies one estimate above the low threshold restarts the count."""
    brood_break = _count([10] * 40 + [31] + [10] * 47)
    assert brood_break.since is None
    assert brood_break.low_since == START + 41 * HOUR
    assert brood_break.low_count == 47

    brood_break = _count([10], brood_break, first_hour=START + 88 * HOUR)
    assert brood_break.since == START + 41 * HOUR


def test_GIVEN_break_WHEN_24_estimates_above_end_level_THEN_break_ends() -> None:
    """Verifies a break ends after 24 estimates in a row above the end level."""
    in_break = BroodBreak(since=START - 100 * HOUR, last_hour=START - HOUR)

    brood_break = _count([46] * 23, in_break)  # top of frames: the end level is 45%
    assert brood_break.since == START - 100 * HOUR
    assert brood_break.end_count == 23

    brood_break = _count([46], brood_break, first_hour=START + 23 * HOUR)
    assert brood_break == BroodBreak(last_hour=START + 23 * HOUR)


def test_GIVEN_break_WHEN_estimates_between_low_and_end_level_THEN_break_continues() -> None:
    """Verifies an estimate between the low threshold and end level restarts the end count."""
    in_break = BroodBreak(since=START - 100 * HOUR, last_hour=START - HOUR)

    brood_break = _count([50] * 23 + [45] + [50] * 23, in_break)

    assert brood_break.since == START - 100 * HOUR
    assert brood_break.end_count == 23


@pytest.mark.parametrize(
    ("hours", "top_of_frames", "in_comb"),
    [
        (FULL_BROOD, "above end", "above end"),
        (PARTIAL_BROOD, "above end", "above end"),
        (SMALL_BROOD, "low", "low"),
        (NO_BROOD, "low", "low"),
        (NO_BROOD_HEATWAVE, "low", "low"),
        (FULL_BROOD_HEATWAVE, "above end", "above end"),
        (WINTER_CLUSTER, "low", "low"),
        (WINTER_BROOD_RESTARTS, "low", "low"),
        (BROOD_AROUND_COMB_SENSOR, "above end", "above end"),
        (BROOD_BREAK_BEES_PRESENT, "low", "low"),
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
        "brood_around_comb_sensor",
        "brood_break_bees_present",
    ],
)
def test_GIVEN_reference_scenarios_WHEN_break_thresholds_THEN_count_as_specified(
    hours: list[tuple[float, float]], top_of_frames: str, in_comb: str
) -> None:
    """Verifies the thresholds per position sort the scenarios as BROOD_ESTIMATE.md 7.6 says."""
    assert _counts_as(_estimate(hours, POSITION_TOP_OF_FRAMES), POSITION_TOP_OF_FRAMES) == (
        top_of_frames
    )
    assert _counts_as(_estimate(hours, POSITION_IN_COMB), POSITION_IN_COMB) == in_comb


def test_GIVEN_gap_of_24_hours_WHEN_counting_THEN_count_continues() -> None:
    """Verifies a gap of up to 24 hours without an estimate neither counts nor resets."""
    brood_break = _count([10] * 30)  # last estimate at START + 29 h

    brood_break = _count([10], brood_break, first_hour=START + 53 * HOUR)

    assert brood_break.low_since == START
    assert brood_break.low_count == 31


def test_GIVEN_gap_over_24_hours_WHEN_counting_THEN_count_starts_over_and_break_kept() -> None:
    """Verifies a longer gap restarts a count in progress, but keeps a break that started."""
    brood_break = _count([10] * 30)
    brood_break = _count([10], brood_break, first_hour=START + 54 * HOUR)
    assert brood_break.low_since == START + 54 * HOUR
    assert brood_break.low_count == 1

    in_break = BroodBreak(since=START - 100 * HOUR, end_count=10, last_hour=START - HOUR)
    brood_break = _count([50], in_break, first_hour=START + 24 * HOUR)
    assert brood_break.since == START - 100 * HOUR
    assert brood_break.end_count == 1


def test_GIVEN_estimate_already_counted_WHEN_break_rule_THEN_skipped() -> None:
    """Verifies an estimate counts once, also when it is made again after a restart."""
    brood_break = _count([10] * 3)

    assert count_brood_break(brood_break, START + 2 * HOUR, 10, POSITION_TOP_OF_FRAMES) == (
        brood_break
    )
    assert count_brood_break(brood_break, START, 10, POSITION_TOP_OF_FRAMES) == brood_break


def test_GIVEN_in_comb_position_WHEN_break_rule_THEN_its_thresholds_apply() -> None:
    """Verifies the in-comb thresholds: low is 15% or less, the end level 30%."""
    assert _count([16] * 48, position=POSITION_IN_COMB).since is None
    in_break = _count([15] * 48, position=POSITION_IN_COMB)
    assert in_break.since == START

    brood_break = _count(
        [31] * 24, in_break, first_hour=START + 48 * HOUR, position=POSITION_IN_COMB
    )
    assert brood_break.since is None
