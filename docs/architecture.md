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
│    daily    (rollups, 31d)                                        │
│        ▲                                                          │
│        │                                                          │
│  HTTP server (:8080)  /  /api  /healthz                           │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

- **Scheduler thread**: sleeps until the next `RUN_MINUTE` (computed in UTC), runs
  `speedtest --accept-license --accept-gdpr -f json`, parses the result and stores it.
  A failed test is logged and skipped, and nothing is stored for that hour.
- **HTTP server**: `ThreadingHTTPServer`. Each request reads SQLite, builds the payload and
  renders the page. The data is embedded in the HTML as JSON, so the page makes no API calls.
- **Front end**: one static HTML template with Chart.js loaded from a CDN. It follows the
  light or dark system theme and reloads itself every 5 minutes.

## Units

The Ookla CLI reports `bandwidth` in bytes per second. The app stores Mbps:

```
Mbps = bandwidth × 8 ÷ 1 000 000
```

Ping is the CLI's `ping.latency`, in milliseconds.

## Tables

### `results`

| Column | Type | Notes |
|---|---|---|
| `ts` | INTEGER, primary key | Unix time (UTC) of the test |
| `down` | REAL | Download, in Mbps |
| `up` | REAL | Upload, in Mbps |
| `ping` | REAL | Latency, in ms |

Rows older than 25 hours are deleted on every insert.

### `daily`

| Column | Type | Notes |
|---|---|---|
| `day` | TEXT, primary key | Date in `DISPLAY_TZ`, `YYYY-MM-DD` |
| `n` | INTEGER | Number of results that day |
| `<m>_sum`, `<m>_min`, `<m>_max` | REAL | For each `m` in `down`, `up`, `ping` |

Each result is upserted into its day: `n` increases by one, the value is added to the sum,
and min and max are updated. Rows older than 31 days are deleted on every insert. Keeping
the sum, rather than a stored average, makes the multi-day averages exact.

## Statistics

Let *today* be the current date in `DISPLAY_TZ`, and *k days ago* mean *today − k*.

### Last 7 days

Covers the days from 0 to 6 days ago:

- avg = Σ sums ÷ Σ counts, which is the true mean of every hourly result
- min = the lowest daily minimum
- max = the highest daily maximum

### Last 30 days

The days from 0 to 29 days ago are split into rolling buckets:

| Bucket | Days ago |
|---|---|
| 1 | 0–6 |
| 2 | 7–13 |
| 3 | 14–20 |
| 4 | 21–27 |
| 5 | 28–29 (partial) |

Each bucket that has data gets its own avg, min and max, computed as above. Then:

- avg = the mean of the bucket averages
- min = the lowest bucket minimum
- max = the highest bucket maximum

Bucket 5 counts as one week in the average of averages even though it covers only 2 days.
This keeps the definition simple. If you would rather drop it, limit the range in
`stats()` to 28 days.

## Retention summary

| Data | Kept for | Maximum rows |
|---|---|---|
| Raw results | 25 h | about 25 |
| Daily rollups | 31 days | 31 |

## Security notes

- The container runs as an unprivileged user (uid 1000).
- There is no authentication. Expose it only on a trusted LAN, or put it behind a reverse
  proxy with authentication.
- The only outbound traffic is the speed test itself, plus the CDN request for Chart.js
  made by the viewer's browser.
