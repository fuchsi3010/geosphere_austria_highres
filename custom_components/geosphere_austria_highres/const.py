"""Constants and pure helpers for the GeoSphere Austria High-Res Nowcast integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "geosphere_austria_highres"

BASE_URL = "https://dataset.api.hub.geosphere.at/v1"
NOWCAST_RESOURCE = "/timeseries/forecast/nowcast-v1-15min-1km"

# Parameters requested from the nowcast endpoint, in a stable order.
PARAMETERS = ("rr", "pt", "t2m", "td", "rh2m", "ff", "dd", "fx")

# Austria bounding box: (lat_min, lat_max, lon_min, lon_max).
BBOX = (45.50, 49.48, 8.10, 17.74)

# The model issues a new run every 15 min on the UTC quarter-hours
# (:00/:15/:30/:45). We poll just *after* each run publishes — see PUBLISH_OFFSET
# — instead of on a fixed interval, so data is fresh and we don't re-pull a run.
RUN_INTERVAL = timedelta(minutes=15)
# Base wait past each quarter-hour before fetching, to let the new run publish.
# Kept short for freshness; a late publish is caught by the staleness retry.
PUBLISH_OFFSET = timedelta(seconds=30)
# Random spread added on top of the offset, drawn once per coordinator, so many
# installs don't all hit the API at the same second.
PUBLISH_JITTER = timedelta(seconds=90)
# If a fetch returns the same reference_time as before (publish ran late), retry
# after this short delay instead of waiting a full run — capped to avoid a storm.
# Live checks show GeoSphere publishes runs ~10 min after their nominal time
# (at :08 the newest run can still be the :45 one), so chase for up to ~12 min
# past the boundary; 3 retries (~5 min) always gave up before the run appeared.
STALENESS_RETRY = timedelta(seconds=90)
MAX_STALENESS_RETRIES = 8
# After a failed fetch, retry sooner than the next publish boundary.
FAILURE_RETRY = timedelta(minutes=2)
# Absolute floor between real network calls: an unscheduled refresh (manual
# reload / update_entity) arriving sooner reuses cache, so the open API can
# never be hammered. Every scheduled wake is comfortably above this.
MIN_FETCH_SPACING = timedelta(seconds=60)

# Alert threshold (mm per 15-min step): drives rain_expected / minutes_until_rain.
RAIN_THRESHOLD_MM = 0.1
# Heavier threshold (mm per 15-min step) for the "downpour" countdown. 1.0 mm /
# 15 min == 4 mm/h, matching CONDITION_POURING_MMH below, so the sensor counts
# down to genuinely heavy rain rather than any drizzle.
DOWNPOUR_THRESHOLD_MM = 1.0
# Weather *condition* is derived from a precip RATE (mm/h) instead, so current
# (15-min) and hourly inputs are comparable, and deliberately higher than the
# alert threshold so light drizzle reads as cloudy rather than rainy.
CONDITION_RAINY_MMH = 0.5
CONDITION_POURING_MMH = 4.0
REQUEST_TIMEOUT = 10
STEP_MINUTES = 15
STEPS_PER_HOUR = 4
# Each timestamp labels the END of its 15-min accumulation window (the first
# timestamp is reference_time + 15 min). Countdowns subtract this to point at
# the window START — when rain can actually begin.
STEP_DELTA = timedelta(minutes=STEP_MINUTES)

ATTRIBUTION = "Data: GeoSphere Austria Data Hub (CC BY 4.0)"

CONF_RAIN_THRESHOLD = "rain_threshold"
CONF_DOWNPOUR_THRESHOLD = "downpour_threshold"

# HA condition string literals (public, stable values) — kept as literals so
# this module stays import-light (it is loaded during the config flow).
COND_RAINY = "rainy"
COND_POURING = "pouring"
COND_SNOWY = "snowy"
COND_SNOWY_RAINY = "snowy-rainy"
COND_PARTLYCLOUDY = "partlycloudy"

# Precipitation-type code -> text. Codes 2-5 are GeoSphere's documented scheme
# but UNVERIFIED against live data (only 0/255=none and 1=rain seen so far).
# TODO: confirm with datahub.support@geosphere.at.
PT_MAP = {
    255: "none",
    0: "none",
    1: "rain",
    2: "rain",
    3: "snow",
    4: "sleet",
    5: "freezing_rain",
}

PRECIP_TYPE_OPTIONS = sorted(set(PT_MAP.values()) | {"precipitation"})


def pt_to_text(code: float | int | None) -> str:
    """Map a precipitation-type code to text, never raising on bad input."""
    try:
        return PT_MAP.get(int(round(code)), "precipitation")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "precipitation"


def derive_condition(rate_mmh: float | None, pt_code: float | int | None) -> str:
    """Derive an HA weather condition from precip *rate* (mm/h) + type.

    No cloud-cover parameter exists, so when it is dry we can only say
    "partlycloudy" — we cannot distinguish sunny from cloudy.
    """
    text = pt_to_text(pt_code)
    if text == "snow":
        return COND_SNOWY
    if text in ("sleet", "freezing_rain"):
        return COND_SNOWY_RAINY
    if rate_mmh is None:
        return COND_PARTLYCLOUDY
    if rate_mmh >= CONDITION_POURING_MMH:
        return COND_POURING
    if rate_mmh >= CONDITION_RAINY_MMH:
        return COND_RAINY
    return COND_PARTLYCLOUDY
