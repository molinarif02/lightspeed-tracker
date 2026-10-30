<img src="static/favicon.svg" alt="" width="72" align="right">

# Lightspeed Tracker

A minimal, self-hosted internet speed tracker that runs in a single container.
Every hour it runs a short burst of Ookla Speedtest CLI tests and keeps the best result,
stores it in a tiny SQLite database,
and serves one page with:

- a **24-hour chart** of download, upload and ping (timestamps in your configured time zone)
- a smaller **last 7 days, per day** chart: the daily average as a line, with the daily min–max
  range as a shaded band for download and upload. Hover a day to see avg, min, max and the number of tests.
- a **last 30 days** table: average, minimum and maximum computed from weekly values

Built for a Raspberry Pi 5 (arm64), and also runs on x86_64 (amd64). The app uses only the Python
standard library: no web framework, no external database, no scheduler daemon.

## Quick start

A prebuilt multi-arch image is published to GitHub Container Registry by GitHub Actions on
every push to `main` and on every version tag. It covers `linux/amd64` (x86_64) and
`linux/arm64` (Raspberry Pi 4/5 with a 64-bit OS). Docker pulls the right one automatically.

```bash
git clone https://github.com/molinarif02/lightspeed-tracker.git
cd lightspeed-tracker
docker compose pull
docker compose up -d
```

Open `http://<host>:8080`. The first result appears about 4 minutes after startup, then every hour at `:00`.

To build the image locally instead:

```bash
docker compose up -d --build
```

With Podman, the same commands work with `podman-compose`.

### Image tags

| Tag | Points to |
|---|---|
| `latest` | The latest build of `main` |
| `1.2.3`, `1.2` | Release tags (`v1.2.3`) |
| `sha-abc1234` | A specific commit |

```
ghcr.io/molinarif02/lightspeed-tracker:latest
```

## Configuration

All settings are environment variables in `compose.yaml`.

| Variable | Default | Description |
|---|---|---|
| `DISPLAY_TZ` | `UTC` | IANA time zone used for chart labels and for day boundaries |
| `RUN_MINUTE` | `0` | Minute past each hour when the result is taken (0–59) |
| `PRE_TESTS` | `3` | Extra runs, one per minute, before each scheduled run (`0` = single run) |
| `SPEEDTEST_SERVER_ID` | *(auto)* | Pin a specific Ookla server ID |
| `PORT` | `8080` | Port the web UI listens on inside the container |
| `DB_PATH` | `/data/lightspeed.db` | SQLite database location |

See [docs/configuration.md](docs/configuration.md) for details.

## Endpoints

| Path | Description |
|---|---|
| `/`, `/index.html` | Web UI (rendered from `index.html`) |
| `/api` | The same data as JSON |
| `/healthz` | Liveness check, returns `ok` |
| `/favicon.svg`, `/favicon.ico`, `/apple-touch-icon.png` | Icons, cached for 7 days |

## How the stats work

- **Each hour is a burst of runs**: with the defaults, tests run at `:57`, `:58`, `:59` and `:00`.
  The hourly result takes the **best value of each metric** across those runs (highest download,
  highest upload, lowest ping), which may come from different runs. It's stamped at `:00`,
  and the per-run samples are deleted once it's saved. Failed runs are ignored.
- Raw hourly results are kept for **25 hours**, which is enough for the 24h chart.
- One summary row per day (count, sum, min, max) is kept for **30 days**: today and the 29 previous days.
- Anything older is deleted every hour (and at startup), even when tests fail, and the
  database file is compacted (`VACUUM`) when a day drops out.
- **7 days, per day**: for each of today and the 6 previous days, the exact daily average
  (sum ÷ count) plus that day's minimum and maximum. Today is still in progress.
- **30 days**: the period is split into rolling 7-day buckets going back from today (4 full
  weeks plus a partial 2-day bucket). The table shows the average of the weekly averages,
  the lowest weekly minimum and the highest weekly maximum.

The database never grows past about 55 rows (a few KB on disk). See [docs/architecture.md](docs/architecture.md).

## Publishing with Cloudflare Tunnel

`compose.yaml` includes an optional `cloudflared` sidecar, enabled by a Compose profile:

```bash
cp .env.example .env      # set TUNNEL_TOKEN
docker compose up -d      # COMPOSE_PROFILES=tunnel in .env starts cloudflared too
```

In the Cloudflare dashboard, point the tunnel's public hostname at `http://lightspeed:8080`.
The page has no login of its own, so protect the hostname with Cloudflare Access.
See [docs/cloudflare-tunnel.md](docs/cloudflare-tunnel.md).

## Documentation

- [Configuration](docs/configuration.md)
- [Architecture and data model](docs/architecture.md)
- [Operations: updates, backup, troubleshooting](docs/operations.md)
- [Publishing with Cloudflare Tunnel](docs/cloudflare-tunnel.md)

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
