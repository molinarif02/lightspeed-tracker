# Lightspeed Tracker

A minimal, self-hosted internet speed tracker that runs in a single container.
It runs the official Ookla Speedtest CLI every hour, keeps a tiny SQLite database,
and serves one page with:

- a **24-hour chart** of download, upload and ping (timestamps in `Europe/Rome` by default)
- **last 7 days**: average, minimum and maximum of all hourly results
- **last 30 days**: average, minimum and maximum computed from weekly values

Built for a Raspberry Pi 5 (arm64), and also runs on x86_64. The app uses only the Python
standard library: no web framework, no external database, no scheduler daemon.

## Quick start

```bash
git clone https://github.com/molinarif02/lightspeed-tracker.git
cd lightspeed-tracker
docker compose up -d --build
```

Open `http://<host>:8080`. The first test runs right after startup, then every hour at `:00`.

With Podman:

```bash
podman-compose up -d --build
```

## Configuration

All settings are environment variables in `compose.yaml`.

| Variable | Default | Description |
|---|---|---|
| `DISPLAY_TZ` | `Europe/Rome` | IANA time zone used for chart labels and for day boundaries |
| `RUN_MINUTE` | `0` | Minute past each hour when the test runs (0–59) |
| `SPEEDTEST_SERVER_ID` | *(auto)* | Pin a specific Ookla server ID |
| `PORT` | `8080` | Port the web UI listens on inside the container |
| `DB_PATH` | `/data/lightspeed.db` | SQLite database location |

See [docs/configuration.md](docs/configuration.md) for details.

## Endpoints

| Path | Description |
|---|---|
| `/` | Web UI |
| `/api` | The same data as JSON |
| `/healthz` | Liveness check, returns `ok` |

## How the stats work

- Raw hourly results are kept for **25 hours**, which is enough for the 24h chart.
- One summary row per day (count, sum, min, max) is kept for **31 days**.
- **7 days**: the exact average (total sum ÷ total count), plus the lowest minimum and highest maximum.
- **30 days**: the period is split into rolling 7-day buckets going back from today (4 full
  weeks plus a partial 2-day bucket). The table shows the average of the weekly averages,
  the lowest weekly minimum and the highest weekly maximum.

The database never grows past about 60 rows. See [docs/architecture.md](docs/architecture.md).

## Documentation

- [Configuration](docs/configuration.md)
- [Architecture and data model](docs/architecture.md)
- [Operations: updates, backup, troubleshooting](docs/operations.md)

## Third-party software

The container image downloads the **Ookla Speedtest CLI** at build time. It is proprietary
software and is **not** distributed with this repository or covered by its license. The app
runs it with `--accept-license --accept-gdpr`. By building and running the image, you accept
Ookla's [EULA](https://www.speedtest.net/about/eula), [terms of use](https://www.speedtest.net/about/terms)
and [privacy policy](https://www.speedtest.net/about/privacy).

The web UI loads [Chart.js](https://www.chartjs.org/) (MIT) from the jsDelivr CDN.

## License

Copyright (C) 2026 Federico Molinari

This program is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version. See [LICENSE](LICENSE).
