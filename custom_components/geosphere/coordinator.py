"""Update coordinator + pure derivation helpers for GeoSphere nowcast data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from statistics import mean, mode
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GeoSphereApiClient, GeoSphereApiError
from .const import (
    MIN_TIME_BETWEEN_UPDATES,
    PARAMETERS,
    RAIN_THRESHOLD_MM,
    STEPS_PER_HOUR,
    derive_condition,
    pt_to_text,
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
    """Polls the nowcast endpoint on an interval, with a hard request floor."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: GeoSphereApiClient,
        latitude: float,
        longitude: float,
        name: str,
        update_interval: timedelta,
        rain_threshold: float = RAIN_THRESHOLD_MM,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
            # Skip needless entity state writes when the payload is unchanged.
            always_update=False,
        )
        self.client = client
        self.latitude = latitude
        self.longitude = longitude
        self.rain_threshold = rain_threshold
        self._last_fetch: datetime | None = None

    async def _async_update_data(self) -> GeoSphereData:
        """Fetch + parse, but never hit the network faster than the floor."""
        now = dt_util.utcnow()
        if (
            self.data is not None
            and self._last_fetch is not None
            and now - self._last_fetch < MIN_TIME_BETWEEN_UPDATES
        ):
            # Too soon since the last real call (e.g. a reload) — reuse cache.
            return self.data

        try:
            raw = await self.client.async_get_nowcast(self.latitude, self.longitude)
        except GeoSphereApiError as err:
            raise UpdateFailed(str(err)) from err

        data = _parse_nowcast(raw)
        self._last_fetch = now
        return data


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


def precip_now(data: GeoSphereData) -> float | None:
    """Precip in the first (next-15-min) step."""
    rr = data.params.get("rr") or []
    return rr[0] if rr else None


def precip_next_hour(data: GeoSphereData) -> float | None:
    """Sum of precip over the next hour (4 steps), skipping gaps."""
    rr = (data.params.get("rr") or [])[:STEPS_PER_HOUR]
    vals = [v for v in rr if v is not None]
    return round(sum(vals), 2) if vals else None


def minutes_until_rain(
    data: GeoSphereData, threshold: float = RAIN_THRESHOLD_MM
) -> int | None:
    """Whole minutes until the first step that rains, or None within horizon."""
    rr = data.params.get("rr") or []
    pt = data.params.get("pt") or []
    now = dt_util.utcnow()
    for i, ts in enumerate(data.timestamps):
        if ts is None:
            continue
        rr_i = rr[i] if i < len(rr) else None
        pt_i = pt[i] if i < len(pt) else None
        rains = (rr_i is not None and rr_i >= threshold) or (
            pt_i is not None and pt_to_text(pt_i) != "none"
        )
        if rains:
            minutes = (ts - now).total_seconds() / 60
            return max(0, int(round(minutes)))
    return None


def rain_expected(
    data: GeoSphereData, threshold: float = RAIN_THRESHOLD_MM
) -> bool:
    """True if any of the next-hour steps reaches the rain threshold."""
    rr = (data.params.get("rr") or [])[:STEPS_PER_HOUR]
    return any(v is not None and v >= threshold for v in rr)


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
        pt_mode = mode(pt_vals) if pt_vals else None
        t_vals = _values_at(t2m, idxs)
        h_vals = _values_at(rh2m, idxs)
        w_vals = _values_at(ff, idxs)
        d_vals = _values_at(dd, idxs)
        forecast.append(
            {
                "datetime": hour,
                "condition": derive_condition(rr_sum, pt_mode),
                "precipitation": rr_sum,
                "temperature": round(mean(t_vals), 2) if t_vals else None,
                "humidity": round(mean(h_vals), 2) if h_vals else None,
                "wind_speed": round(mean(w_vals), 2) if w_vals else None,
                "wind_bearing": round(mean(d_vals)) if d_vals else None,
            }
        )
    return forecast
