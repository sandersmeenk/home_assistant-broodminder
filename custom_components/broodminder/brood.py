"""Brood estimate from the in-hive and outdoor temperature, and the likely brood break.

A colony with brood keeps the brood nest at about 35 °C, whatever the weather. Without brood,
the hive follows the outdoor temperature. Per hour, the estimate scores how far the colony
keeps the hive sensor above what the weather alone would give, towards 35 °C. The day's score
is then lowered when the hive swings along with the outdoor temperature.

A likely brood break starts when the estimate stays low for two days, and ends when it stays
clearly higher for a day.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import quantiles

from .const import (
    BROOD_BREAK_END_HOURS,
    BROOD_BREAK_END_PERCENT,
    BROOD_BREAK_LOW_PERCENT,
    BROOD_BREAK_MAX_GAP_HOURS,
    BROOD_BREAK_START_HOURS,
    BROOD_EDGE_TEMP_C,
    BROOD_MIN_HOURS,
    BROOD_STATUS_NOT_ENOUGH_DATA,
    BROOD_STATUS_OK,
    BROOD_STATUS_TOO_HOT,
    BROOD_TEMP_C,
    BROOD_WINDOW_HOURS,
    COLONY_WARMING_C,
    MIN_OUTDOOR_SWING_C,
    STABLE_SWING_RATIO,
)

SECONDS_PER_HOUR = 3600
# Percentiles for the daily swing: 5th to 95th ignores a single odd hour
SWING_QUANTILES = 20


@dataclass
class HourlyTemperatures:
    """Running sums of one hour's samples, averaged once the hour is complete."""

    hour: int  # start of the hour, in seconds since the epoch
    hive_sum: float = 0.0
    hive_count: int = 0
    outdoor_sum: float = 0.0
    outdoor_count: int = 0

    def add(self, hive_c: float | None, outdoor_c: float | None) -> None:
        """Add a sample; a missing temperature is skipped."""
        if hive_c is not None:
            self.hive_sum += hive_c
            self.hive_count += 1
        if outdoor_c is not None:
            self.outdoor_sum += outdoor_c
            self.outdoor_count += 1

    @property
    def hive_c(self) -> float | None:
        """Return the hour's mean hive temperature."""
        return self.hive_sum / self.hive_count if self.hive_count else None

    @property
    def outdoor_c(self) -> float | None:
        """Return the hour's mean outdoor temperature."""
        return self.outdoor_sum / self.outdoor_count if self.outdoor_count else None


@dataclass(frozen=True)
class BroodEstimate:
    """Brood estimate over the last 24 hours."""

    status: str
    brood_percent: int | None = None
    level: float | None = None  # mean hourly score, 0..1
    stability: float | None = None  # 0..1, 1 when the hive doesn't follow the weather
    hours_used: int = 0


@dataclass(frozen=True)
class BroodBreak:
    """Likely brood break, and the counts in progress that start or end one."""

    since: int | None = None  # start of the likely brood break, in seconds since the epoch
    low_since: int | None = None  # first estimate of the low count in progress
    low_count: int = 0
    end_count: int = 0  # estimates in a row above the end level, during a break
    last_hour: int | None = None  # time of the last counted estimate


def hour_start(timestamp: float) -> int:
    """Return the start of the hour containing timestamp, in seconds since the epoch."""
    return int(timestamp) // SECONDS_PER_HOUR * SECONDS_PER_HOUR


def brood_window(hours: list[HourlyTemperatures], current_hour: int) -> list[tuple[float, float]]:
    """Return (hive, outdoor) means of the complete hours in the window that have both."""
    first_hour = current_hour - BROOD_WINDOW_HOURS * SECONDS_PER_HOUR
    window = []
    for hour in sorted(hours, key=lambda h: h.hour):
        if not first_hour <= hour.hour < current_hour:
            continue
        hive_c, outdoor_c = hour.hive_c, hour.outdoor_c
        if hive_c is not None and outdoor_c is not None:
            window.append((hive_c, outdoor_c))
    return window


def estimate_brood(hours: list[tuple[float, float]], position: str) -> BroodEstimate:
    """Estimate brood from hourly (hive, outdoor) mean temperatures in °C."""
    if len(hours) < BROOD_MIN_HOURS:
        return BroodEstimate(BROOD_STATUS_NOT_ENOUGH_DATA, hours_used=len(hours))

    level = _level(hours, BROOD_EDGE_TEMP_C[position])
    if level is None:
        return BroodEstimate(BROOD_STATUS_TOO_HOT, hours_used=len(hours))

    stability = _stability([hive for hive, _ in hours], [outdoor for _, outdoor in hours])
    return BroodEstimate(
        BROOD_STATUS_OK,
        brood_percent=round(100 * level * stability),
        level=level,
        stability=stability,
        hours_used=len(hours),
    )


def count_brood_break(
    brood_break: BroodBreak, hour: int, brood_percent: int, position: str
) -> BroodBreak:
    """Return the likely brood break after the brood estimate made for hour.

    hour is the end of the estimate's window. An estimate that was already counted, for
    example before a restart, changes nothing.
    """
    if brood_break.last_hour is not None:
        if hour <= brood_break.last_hour:
            return brood_break
        if hour - brood_break.last_hour > BROOD_BREAK_MAX_GAP_HOURS * SECONDS_PER_HOUR:
            # Estimates weeks apart don't make a count; a break that has started is kept
            brood_break = BroodBreak(since=brood_break.since)

    if brood_break.since is None:
        if brood_percent > BROOD_BREAK_LOW_PERCENT[position]:
            return BroodBreak(last_hour=hour)
        low_since = hour if brood_break.low_since is None else brood_break.low_since
        low_count = brood_break.low_count + 1
        if low_count >= BROOD_BREAK_START_HOURS:
            # Shown from the first low estimate, so the days count from the drop
            return BroodBreak(since=low_since, last_hour=hour)
        return BroodBreak(low_since=low_since, low_count=low_count, last_hour=hour)

    if brood_percent <= BROOD_BREAK_END_PERCENT[position]:
        return BroodBreak(since=brood_break.since, last_hour=hour)
    end_count = brood_break.end_count + 1
    if end_count >= BROOD_BREAK_END_HOURS:
        return BroodBreak(last_hour=hour)
    return BroodBreak(since=brood_break.since, end_count=end_count, last_hour=hour)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _level(hours: list[tuple[float, float]], edge_c: float) -> float | None:
    """Return the weighted mean hourly score, or None if every hour was too hot to judge."""
    weighted_score = 0.0
    total_weight = 0.0
    for hive_c, outdoor_c in hours:
        # What the hive would be without brood: outdoors plus the colony's warmth, but at
        # least the edge of the brood range, so a warm broodless cluster doesn't count
        reference_c = max(outdoor_c + COLONY_WARMING_C, edge_c)
        span_c = BROOD_TEMP_C - reference_c
        if span_c <= 0:
            continue  # so hot outdoors that brood temperature says nothing
        # Warm hours count less: the less room the weather leaves, the less the hour says
        weighted_score += span_c * _clamp((hive_c - reference_c) / span_c)
        total_weight += span_c

    return weighted_score / total_weight if total_weight else None


def _swing(temperatures: list[float]) -> float:
    cut_points = quantiles(temperatures, n=SWING_QUANTILES, method="inclusive")
    return cut_points[-1] - cut_points[0]


def _stability(hive: list[float], outdoor: list[float]) -> float:
    """Return 1 when the hive keeps steady while the weather swings, 0 when it follows it."""
    outdoor_swing = _swing(outdoor)
    if outdoor_swing < MIN_OUTDOOR_SWING_C:
        return 1.0
    return _clamp((1 - _swing(hive) / outdoor_swing) / (1 - STABLE_SWING_RATIO))
