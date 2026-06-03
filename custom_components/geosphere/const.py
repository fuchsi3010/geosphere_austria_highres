"""Constants and pure helpers for the GeoSphere Austria integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "geosphere"

BASE_URL = "https://dataset.api.hub.geosphere.at/v1"
NOWCAST_RESOURCE = "/timeseries/forecast/nowcast-v1-15min-1km"

# Parameters requested from the nowcast endpoint, in a stable order.
PARAMETERS = ("rr", "pt", "t2m", "td", "rh2m", "ff", "dd", "fx")

# Austria bounding box: (lat_min, lat_max, lon_min, lon_max).
BBOX = (45.50, 49.48, 8.10, 17.74)

# The nowcast is re-issued every 15 min; polling every 10 min is gentle and
# guarantees we never miss a run by much.
DEFAULT_SCAN_INTERVAL = timedelta(minutes=10)
# Hard floor between *actual* network calls, independent of scheduled polls,
# so manual reloads or extra refreshes can never hammer the open API.
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)
MIN_SCAN_INTERVAL_MINUTES = 5

RAIN_THRESHOLD_MM = 0.1
POURING_MM = 2.5
REQUEST_TIMEOUT = 10
STEP_MINUTES = 15
STEPS_PER_HOUR = 4

ATTRIBUTION = "Data: GeoSphere Austria Data Hub (CC BY 4.0)"

CONF_RAIN_THRESHOLD = "rain_threshold"

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


def derive_condition(rr_mm: float | None, pt_code: float | int | None) -> str:
    """Derive an HA weather condition from precip amount + type.

    No cloud-cover parameter exists, so when it is dry we can only say
    "partlycloudy" — we cannot distinguish sunny from cloudy.
    """
    text = pt_to_text(pt_code)
    if text == "snow":
        return COND_SNOWY
    if text in ("sleet", "freezing_rain"):
        return COND_SNOWY_RAINY
    if rr_mm is None:
        return COND_PARTLYCLOUDY
    if rr_mm >= POURING_MM:
        return COND_POURING
    if rr_mm >= RAIN_THRESHOLD_MM:
        return COND_RAINY
    return COND_PARTLYCLOUDY
