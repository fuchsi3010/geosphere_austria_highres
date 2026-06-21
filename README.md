# GeoSphere Austria High-Res Nowcast — Home Assistant integration

Near-real-time **rain nowcasting** for any point in Austria, using the
[GeoSphere Austria Data Hub](https://data.hub.geosphere.at/) **INCA nowcast**
(`nowcast-v1-15min-1km`): a 1 km grid, re-issued every 15 minutes, with
precipitation in 15-minute steps ~3 hours ahead.

Because it is a *forecast*, you get a ~15-minute **lead** ("rain starts in
15 min") instead of the ~10–20-minute *lag* you get from observation-only
station integrations — so rain automations can fire **before** it rains.

> **Not the same as the core [`zamg`](https://www.home-assistant.io/integrations/zamg/)
> integration.** That one (also "GeoSphere Austria") exposes *observed* data from
> physical weather stations. This one exposes the *forecast* INCA nowcast for any
> 1 km grid point — they are complementary, and you can run both.

> Data: GeoSphere Austria Data Hub, licensed **CC BY 4.0**. The API is open and
> needs no API key. This integration polls gently — aligned to the model's
> 15-minute publish cadence (a few seconds after each new run, with random
> jitter so installs don't sync up), with a 10 s timeout — well under the API's
> rate limits.
>
> *Not affiliated with or endorsed by GeoSphere Austria. "GeoSphere Austria" is
> used only to identify the data source. The icon is original artwork, not
> GeoSphere's logo.*

## Installation

### Option A — HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/fuchsi3010/geosphere_austria_highres`, category
   **Integration**.
2. Install **GeoSphere Austria High-Res Nowcast**, then restart Home Assistant.

### Option B — Manual
Copy `custom_components/geosphere_austria_highres/` into your HA
`config/custom_components/` directory and restart Home Assistant.

## Configuration

**Settings → Devices & Services → Add Integration → "GeoSphere Austria High-Res Nowcast"**.
A map appears defaulting to your **Home** location — accept it or drag the
marker to any point in Austria, give it a name, and submit. Add multiple
points by adding the integration again.

Options (gear icon on the entry):

| Option | Default | Notes |
|---|---|---|
| Rain threshold | `0.1` mm/15 min | Drives "rain expected" + "minutes until rain". |
| Downpour threshold | `1.0` mm/15 min | Drives "minutes until downpour" (≈ 4 mm/h, the "pouring" rate). |
| Update interval | `10` min | Minimum `5`. The API re-issues every 15 min. |

## Entities

Per configured point you get one device with:

- **`weather.*`** — current conditions (from the next 15-min step) + an
  **hourly** forecast for the ~3 h horizon.
- **`sensor.*_precipitation`** — precip in the next 15 min (mm).
- **`sensor.*_precipitation_next_hour`** — summed precip over the next hour (mm).
- **`sensor.*_minutes_until_rain`** — minutes until the first raining step.
- **`sensor.*_minutes_until_downpour`** — minutes until the first step reaching
  the *downpour* threshold (heavy rain only). `unknown` when none is forecast.
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

## Example: warn ~1 h and ~15 min before a downpour

`sensor.*_minutes_until_downpour` counts down to heavy rain only, so it's the
right trigger for "bring it in" alerts. The countdown moves in ~15-min steps
(one model step per refresh), so the band on the 1 h alert makes it fire once
as it crosses ~60.

```yaml
automation:
  - alias: "Downpour — 1 h warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.geosphere_home_minutes_until_downpour
        above: 45
        below: 75
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Downpour incoming"
          message: "Heavy rain in ~{{ trigger.to_state.state }} min."

  - alias: "Downpour — 15 min warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.geosphere_home_minutes_until_downpour
        below: 16
    action:
      - service: notify.mobile_app_phone
        data:
          title: "Downpour now"
          message: "Heavy rain in ~{{ trigger.to_state.state }} min — bring it in."
```

Fast-developing convection often only enters the nowcast ~30–45 min out, so the
1 h alert can occasionally land late or coincide with the 15-min one — that's
the nature of nowcasting, not the automation.

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
