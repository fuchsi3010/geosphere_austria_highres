"""Update coordinator + pure derivation helpers for GeoSphere nowcast data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import random
from statistics import mean, mode
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GeoSphereApiClient, GeoSphereApiError
from .const import (
    DOWNPOUR_THRESHOLD_MM,
    FAILURE_RETRY,
    MAX_STALENESS_RETRIES,
    MIN_FETCH_SPACING,
    PARAMETERS,
    PUBLISH_JITTER,
    PUBLISH_OFFSET,
    RAIN_THRESHOLD_MM,
    RUN_INTERVAL,
    STALENESS_RETRY,
    STEP_DELTA,
    STEPS_PER_HOUR,
    derive_condition,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class GeoSphereData:
    """Parsed, time-aligned nowcast snapshot for one point."""

    reference_time: datetime | None
    timestamps: list[datetime | None]
    params: dict[str, list[float | None]]
    coordinates: tuple[float, float]


class GeoSphereDataUpdateCoordinator(DataUpdateCoordinator[GeoSphereData]):
    """Polls the nowcast endpoint aligned to the model's publish cadence.

    Rather than a fixed interval, each successful fetch schedules the next wake
    just after the next 15-min publish boundary. If a run published late (we got
    the same ``reference_time`` back), it retries quickly instead of waiting a
    full run.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: GeoSphereApiClient,
        latitude: float,
        longitude: float,
        name: str,
        rain_threshold: float = RAIN_THRESHOLD_MM,
        downpour_threshold: float = DOWNPOUR_THRESHOLD_MM,
    ) -> None:
        # Fixed per-coordinator phase so concurrent installs spread their load.
        self._jitter = timedelta(
            seconds=random.uniform(0, PUBLISH_JITTER.total_seconds())
        )
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            # Corrected after every fetch; the first refresh runs immediately.
            update_interval=_aligned_interval(dt_util.utcnow(), self._jitter),
            # Skip needless entity state writes when the payload is unchanged.
            always_update=False,
        )
        self.client = client
        self.latitude = latitude
        self.longitude = longitude
        self.rain_threshold = rain_threshold
        self.downpour_threshold = downpour_threshold
        self._last_fetch: datetime | None = None
        self._last_reference_time: datetime | None = None
        self._retry_count = 0

    async def _async_update_data(self) -> GeoSphereData:
        """Fetch + parse, then arm the next wake aligned to the publish cadence."""
        now = dt_util.utcnow()
        if (
            self.data is not None
            and self._last_fetch is not None
            and now - self._last_fetch < MIN_FETCH_SPACING
        ):
            # Unscheduled refresh too soon after a real call — reuse cache and
            # leave the existing schedule untouched.
            return self.data

        try:
            raw = await self.client.async_get_nowcast(self.latitude, self.longitude)
        except GeoSphereApiError as err:
            self.update_interval = FAILURE_RETRY
            raise UpdateFailed(str(err)) from err

        data = _parse_nowcast(raw)
        self._last_fetch = now

        is_new_run = data.reference_time != self._last_reference_time
        self._last_reference_time = data.reference_time

        if (
            not is_new_run
            and data.reference_time is not None
            and self._retry_count < MAX_STALENESS_RETRIES
        ):
            # Same run as last time — the new one published late; retry soon.
            self._retry_count += 1
            self.update_interval = STALENESS_RETRY
        else:
            self._retry_count = 0
            self.update_interval = _aligned_interval(now, self._jitter)

        return data


def _aligned_interval(now: datetime, jitter: timedelta) -> timedelta:
    """Delay from ``now`` until just after the next 15-min publish boundary (UTC)."""
    period = RUN_INTERVAL.total_seconds()
    into = (now.minute * 60 + now.second + now.microsecond / 1e6) % period
    offset = PUBLISH_OFFSET.total_seconds() + jitter.total_seconds()
    return timedelta(seconds=(period - into) + offset)


def _parse_nowcast(raw: Any) -> GeoSphereData:
    """Map raw API JSON to a GeoSphereData, raising UpdateFailed on bad shape."""
    if not isinstance(raw, dict):
        raise UpdateFailed("Unexpected response (not an object)")

    features = raw.get("features")
    timestamps_raw = raw.get("timestamps")
    if not features or not timestamps_raw:
        raise UpdateFailed("Empty response (no features/timestamps)")

    feature = features[0]
    try:
        params_block = feature["properties"]["parameters"]
        coords = feature["geometry"]["coordinates"]
    except (KeyError, TypeError) as err:
        raise UpdateFailed("Malformed feature in response") from err

    timestamps = [dt_util.parse_datetime(ts) for ts in timestamps_raw]
    reference_time = dt_util.parse_datetime(raw.get("reference_time") or "")

    params: dict[str, list[float | None]] = {}
    for name in PARAMETERS:
        block = params_block.get(name)
        data = block.get("data") if isinstance(block, dict) else None
        if data is None:
            raise UpdateFailed(f"Missing parameter '{name}' in response")
        params[name] = data

    coordinates = (coords[0], coords[1])  # [lon, lat] as returned (snapped cell)
    return GeoSphereData(reference_time, timestamps, params, coordinates)


# --- Pure derivation helpers (unit-testable; take GeoSphereData, no I/O) ----


def _values_at(arr: list[float | None], idxs: list[int]) -> list[float]:
    return [arr[i] for i in idxs if i < len(arr) and arr[i] is not None]


def _future_window_indices(data: GeoSphereData, now: datetime) -> list[int]:
    """Indices of steps whose accumulation window has not fully passed.

    Timestamps label the END of each 15-min window (first timestamp is
    reference_time + 15 min), and runs publish ~10 min late — so with a stale
    run the leading steps can lie entirely in the past. A step stays relevant
    while its window end is in the future.
    """
    return [
        i for i, ts in enumerate(data.timestamps) if ts is not None and ts > now
    ]


def precip_now(data: GeoSphereData) -> float | None:
    """Precip in the current 15-min window (the first window still open)."""
    rr = data.params.get("rr") or []
    idxs = _future_window_indices(data, dt_util.utcnow())
    if idxs and idxs[0] < len(rr):
        return rr[idxs[0]]
    return rr[0] if rr else None


def precip_next_hour(data: GeoSphereData) -> float | None:
    """Sum of precip over the next hour: the 4 windows still open, skipping gaps."""
    rr = data.params.get("rr") or []
    idxs = _future_window_indices(data, dt_util.utcnow())[:STEPS_PER_HOUR]
    vals = _values_at(rr, idxs)
    return round(sum(vals), 2) if vals else None


def minutes_until_rain(
    data: GeoSphereData, threshold: float = RAIN_THRESHOLD_MM
) -> int | None:
    """Whole minutes until rain can begin, or None within the horizon.

    Keyed purely off precip *amount* (rr >= threshold), consistent with
    ``rain_expected`` and ``minutes_until_downpour`` (an earlier version also
    counted the broadly-set precip-*type* flag — see v0.3.1 notes).

    Counts down to the window START (ts - 15 min, clamped to 0): timestamps
    label the END of each accumulation window, so counting to ts itself
    overstated the lead by up to 15 min — on top of the model's own ~10-min
    publish latency, a "rain in 14 min" push could coincide with the first
    drops (v0.3.2).
    """
    rr = data.params.get("rr") or []
    now = dt_util.utcnow()
    for i, ts in enumerate(data.timestamps):
        if ts is None:
            continue
        rr_i = rr[i] if i < len(rr) else None
        if rr_i is not None and rr_i >= threshold:
            minutes = (ts - STEP_DELTA - now).total_seconds() / 60
            return max(0, int(round(minutes)))
    return None


def minutes_until_downpour(
    data: GeoSphereData, threshold: float = DOWNPOUR_THRESHOLD_MM
) -> int | None:
    """Minutes until the first window reaching the (heavier) downpour threshold.

    Same countdown as :func:`minutes_until_rain`, keyed to intensity: mm per
    15-min window. Returns None if no window within the horizon is that heavy.
    """
    return minutes_until_rain(data, threshold)


def rain_expected(
    data: GeoSphereData, threshold: float = RAIN_THRESHOLD_MM
) -> bool:
    """True if any still-open window in the next hour reaches the threshold."""
    rr = data.params.get("rr") or []
    idxs = _future_window_indices(data, dt_util.utcnow())[:STEPS_PER_HOUR]
    return any(v >= threshold for v in _values_at(rr, idxs))


def hourly_forecast(data: GeoSphereData) -> list[dict[str, Any]]:
    """Bucket the 15-min steps into per-hour forecast dicts."""
    rr = data.params.get("rr") or []
    t2m = data.params.get("t2m") or []
    rh2m = data.params.get("rh2m") or []
    ff = data.params.get("ff") or []
    dd = data.params.get("dd") or []
    pt = data.params.get("pt") or []

    buckets: dict[datetime, list[int]] = {}
    for i, ts in enumerate(data.timestamps):
        if ts is None:
            continue
        hour = ts.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour, []).append(i)

    forecast: list[dict[str, Any]] = []
    for hour in sorted(buckets):
        idxs = buckets[hour]
        rr_vals = _values_at(rr, idxs)
        pt_vals = _values_at(pt, idxs)
        rr_sum = round(sum(rr_vals), 2) if rr_vals else None
        # Condition uses a rate (mm/h) so partial buckets aren't under-counted.
        rr_rate = mean(rr_vals) * STEPS_PER_HOUR if rr_vals else None
        pt_mode = mode(pt_vals) if pt_vals else None
        t_vals = _values_at(t2m, idxs)
        h_vals = _values_at(rh2m, idxs)
        w_vals = _values_at(ff, idxs)
        d_vals = _values_at(dd, idxs)
        forecast.append(
            {
                "datetime": hour,
                "condition": derive_condition(rr_rate, pt_mode),
                "precipitation": rr_sum,
                "temperature": round(mean(t_vals), 2) if t_vals else None,
                "humidity": round(mean(h_vals), 2) if h_vals else None,
                "wind_speed": round(mean(w_vals), 2) if w_vals else None,
                "wind_bearing": round(mean(d_vals)) if d_vals else None,
            }
        )
    return forecast
