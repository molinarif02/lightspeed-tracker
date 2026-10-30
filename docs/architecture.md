# Architecture and data model

## Overview

Everything is one Python process (`app.py`) using only the standard library:

```
┌──────────────────────────── container ────────────────────────────┐
│                                                                   │
│  scheduler thread ── every hour ──► speedtest CLI (Ookla, JSON)   │
│        │                                                          │
│        ▼                                                          │
│  SQLite (/data/lightspeed.db)                                     │
│    results  (raw, 25h)                                            │
│    daily    (rollups, 30d)                                        │
│        ▲                                                          │
│        │                                                          │
│  HTTP server (:8080)  / (index.html)  /api  /healthz              │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

- **Scheduler thread**: each hour it runs a burst of `PRE_TESTS + 1` tests, one per minute,
  ending at `RUN_MINUTE` (computed in UTC). Each run calls
  `speedtest --accept-license --accept-gdpr -f json` and stores the parsed values in `samples`.
  After the last run, the best of each metric (highest download, highest upload, lowest ping)
  becomes the hourly result, stamped at the scheduled time, and that burst's samples are
  deleted. Failed runs are skipped; if every run fails, nothing is stored for that hour.
- **HTTP server**: `ThreadingHTTPServer`. Each request reads SQLite, builds the payload and
  renders the page. The data is embedded in the HTML as JSON, so the page makes no API calls.
- **Front end**: `index.html`, a static template loaded once at startup, with Chart.js from a CDN.
  The app replaces its `__DATA__` placeholder with the JSON payload.
- **Icons**: `static/` holds the favicon (SVG, plus ICO and Apple touch icon fallbacks).
  The files are loaded into memory at startup, and only those exact paths are served. It has two charts
  (the last 24 hours, and the last 7 days per day) and the 30-day table. It follows the
  light or dark system theme and reloads itself every 5 minutes.

## Units

The Ookla CLI reports `bandwidth` in bytes per second. The app stores Mbps:

```
Mbps = bandwidth × 8 ÷ 1 000 000
```

Ping is the CLI's `ping.latency`, in milliseconds.

## Tables

### `samples` (temporary)

| Column | Type | Notes |
|---|---|---|
| `target` | INTEGER | Scheduled time of the burst (unix, UTC) |
| `ts` | INTEGER | When the run finished |
| `down`, `up`, `ping` | REAL | Mbps, Mbps, ms |

It holds at most `PRE_TESTS + 1` rows, and only while a burst is running. Rows are deleted
as soon as the hourly result is saved, even when the burst fails. Any leftovers from a
burst interrupted by a restart are cleared at startup.

Picking the best of each metric independently means one hourly result can combine values
from different runs, for example the download from one run and the ping from another. It
measures what the line can do at its best within those minutes, not a single run.

### `results`

| Column | Type | Notes |
|---|---|---|
| `ts` | INTEGER, primary key | Unix time (UTC) of the test |
| `down` | REAL | Download, in Mbps |
| `up` | REAL | Upload, in Mbps |
| `ping` | REAL | Latency, in ms |

Rows older than 25 hours are deleted by the hourly prune.

### `daily`

| Column | Type | Notes |
|---|---|---|
| `day` | TEXT, primary key | Date in `DISPLAY_TZ`, `YYYY-MM-DD` |
| `n` | INTEGER | Number of results that day |
| `<m>_sum`, `<m>_min`, `<m>_max` | REAL | For each `m` in `down`, `up`, `ping` |

Each result is upserted into its day: `n` increases by one, the value is added to the sum,
and min and max are updated. Keeping
the sum, rather than a stored average, makes the multi-day averages exact.

## Statistics

Let *today* be the current date in `DISPLAY_TZ`, and *k days ago* mean *today − k*.

### Last 7 days, per day (chart)

There is one point per day, from 6 days ago up to today. Each day's values come from its
`daily` row:

- avg = sum ÷ n, the exact mean of that day's hourly results
- min and max = that day's lowest and highest result

Today is still in progress, so it holds fewer results. A day with no results is empty, and
the line is drawn across the gap. On the chart, download and upload show the min–max range as
a shaded band. Ping shows only its average line, since a band on the separate ms axis would
overlap the Mbps bands. The tooltip shows avg, min, max and the test count for all three.

The API also returns `last7`, the 7-day period as a single aggregate (Σ sums ÷ Σ counts, the
lowest minimum and the highest maximum). The page doesn't display it.

### Last 30 days

The days from 0 to 29 days ago are split into rolling buckets:

| Bucket | Days ago |
|---|---|
| 1 | 0–6 |
| 2 | 7–13 |
| 3 | 14–20 |
| 4 | 21–27 |
| 5 | 28–29 (partial) |

Each bucket that has data gets its own avg (Σ sums ÷ Σ counts), min and max. Then:

- avg = the mean of the bucket averages
- min = the lowest bucket minimum
- max = the highest bucket maximum

Bucket 5 counts as one week in the average of averages even though it covers only 2 days.
This keeps the definition simple. If you would rather drop it, limit the range in
`stats()` to 28 days.

## Retention summary

`prune()` runs at startup and after every scheduled test, whether the test succeeded or
failed, so old data is removed even during an outage. When a day drops out of the 30-day
window, which happens about once a day, the database is also compacted with `VACUUM`, so
the file stays small on disk.

| Data | Kept for | Maximum rows |
|---|---|---|
| Burst samples | until the hour's result is saved | `PRE_TESTS + 1` |
| Raw results | 25 h | about 25 |
| Daily rollups | 30 days (today + 29 previous) | 30 |

## Security notes

- The container runs as an unprivileged user (uid 1000).
- There is no authentication. Expose it only on a trusted LAN, or behind something that adds
  authentication, such as Cloudflare Access when publishing through a tunnel.
- Responses carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and
  `Referrer-Policy: no-referrer`.
- The only outbound traffic is the speed test itself, plus the CDN request for Chart.js
  made by the viewer's browser.
