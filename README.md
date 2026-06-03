# GeoSphere Austria — Home Assistant integration

Near-real-time **rain nowcasting** for any point in Austria, using the
[GeoSphere Austria Data Hub](https://data.hub.geosphere.at/) **INCA nowcast**
(`nowcast-v1-15min-1km`): a 1 km grid, re-issued every 15 minutes, with
precipitation in 15-minute steps ~3 hours ahead.

Because it is a *forecast*, you get a ~15-minute **lead** ("rain starts in
15 min") instead of the ~10–20-minute *lag* you get from observation-only
station integrations — so rain automations can fire **before** it rains.

> Data: GeoSphere Austria Data Hub, licensed **CC BY 4.0**. The API is open and
> needs no API key. This integration polls gently (every 10 min by default,
> with a hard 5-minute floor between network calls) and uses a 10 s timeout.

## Installation

### Option A — HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add this repo's URL, category
   **Integration**.
2. Install **GeoSphere Austria**, then restart Home Assistant.

### Option B — Manual
Copy `custom_components/geosphere/` into your HA `config/custom_components/`
directory and restart Home Assistant.

## Configuration

**Settings → Devices & Services → Add Integration → "GeoSphere Austria"**.
A map appears defaulting to your **Home** location — accept it or drag the
marker to any point in Austria, give it a name, and submit. Add multiple
points by adding the integration again.

Options (gear icon on the entry):

| Option | Default | Notes |
|---|---|---|
| Rain threshold | `0.1` mm/15 min | Drives "rain expected" + "minutes until rain". |
| Update interval | `10` min | Minimum `5`. The API re-issues every 15 min. |

## Entities

Per configured point you get one device with:

- **`weather.*`** — current conditions (from the next 15-min step) + an
  **hourly** forecast for the ~3 h horizon.
- **`sensor.*_precipitation`** — precip in the next 15 min (mm).
- **`sensor.*_precipitation_next_hour`** — summed precip over the next hour (mm).
- **`sensor.*_minutes_until_rain`** — minutes until the first raining step.
- **`sensor.*_precipitation_type`** — enum (`none`/`rain`/`snow`/…).
- **`sensor.*_temperature`**, **`sensor.*_humidity`**, **`sensor.*_wind_speed`**.
- **`binary_sensor.*_rain_expected`** — on when rain is forecast within the
  next hour. Its attributes carry `minutes_until_rain`, `reference_time`, and a
  step-by-step `forecast` list — the payload for the automation below.

## Example: notify ~15 minutes before rain

```yaml
automation:
  - alias: "Rain incoming — close the windows"
    trigger:
      - platform: state
        entity_id: binary_sensor.geosphere_home_rain_expected
        to: "on"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Rain incoming"
          message: >-
            Rain expected in
            {{ state_attr('binary_sensor.geosphere_home_rain_expected',
               'minutes_until_rain') }} min.
```

## Limitations

- **Austria only** — points outside the bounding box are rejected in setup.
- **~3 h horizon**, 15-minute resolution; only an *hourly* forecast is exposed
  (a daily forecast would be meaningless at this horizon).
- **No "now" step** — the first forecast step is reference time + 15 min, so the
  "current" weather/sensors really mean "next 15 minutes".
- **No cloud cover** parameter, so when it is dry the condition can only be
  `partlycloudy` (we can't tell sunny from cloudy).
- **Precipitation-type** codes beyond `rain` (snow/sleet/freezing rain) are
  GeoSphere's documented scheme but **unverified** against live data; unknown
  codes fall back to a generic `precipitation` / `rainy`.
