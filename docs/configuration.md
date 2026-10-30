# Configuration

Lightspeed Tracker is configured only through environment variables. With Docker Compose,
set them in the `environment:` section of `compose.yaml`, then run `docker compose up -d`
to apply them. `compose.yaml` ships with `DISPLAY_TZ`, `SPEEDTEST_SERVER_ID` and `PORT`
commented out, so uncomment the ones you want to set.

## Variables

### `DISPLAY_TZ`

Default: `UTC`

An IANA time zone name, such as `Europe/Rome` or `UTC`. It controls:

- the time labels on the 24h chart and in the "Last test" line
- where each day starts and ends for the daily summaries, and so for the 7-day and 30-day stats

Changing it later only affects new data. Days that were already summarised keep the
boundaries they were computed with.

### `RUN_MINUTE`

Default: `0`

The minute past each hour when the hourly result is taken: the last run of each burst
happens at this minute, and the result is stamped with it. The schedule is computed in UTC,
so DST changes never skip or repeat a run. Picking a minute other than `0` (for example `7`)
avoids the busy top of the hour on Ookla's servers.

On startup, if the last stored result is more than 55 minutes old, a burst starts at the
next full minute, so the first result appears about 4 minutes later. That's skipped when
the next scheduled burst is less than about 10 minutes away.

### `PRE_TESTS`

Default: `3`

The number of extra runs before each scheduled run, one per minute. With the default and
`RUN_MINUTE=0`, tests run at `:57`, `:58`, `:59` and `:00`. The hourly result is the best
value of each metric across all successful runs: highest download, highest upload and
lowest ping. Set it to `0` for a single run per hour.

If a run takes longer than a minute, the next one starts as soon as it finishes instead of
overlapping. If the container starts during a burst window, the missed runs happen right away.

Each run transfers real data in both directions. On a gigabit line, a run can move around
1–1.5 GB, so the default of 4 runs per hour adds up to several TB a month. Lower
`PRE_TESTS` if your connection has a data cap.

### `SPEEDTEST_SERVER_ID`

Default: empty, so Ookla picks a server automatically.

Pinning a server keeps results comparable over time. To list nearby servers:

```bash
docker exec lightspeed-tracker speedtest -L
```

Then set it in `compose.yaml`, for example `SPEEDTEST_SERVER_ID=12345`. If the pinned server
goes offline, tests fail and are logged until you change or remove it.

### `PORT`

Default: `8080`

The port the HTTP server listens on inside the container. To expose a different host port,
change the left side of the `ports:` mapping instead, for example `"9000:8080"`. If you change
`PORT`, update the right side of the mapping and the tunnel's service URL to match.

### `PAGE_FILE`

Default: `/app/index.html`

The HTML template for the web UI. To customise the page without rebuilding, mount your own copy:

```yaml
    volumes:
      - ./index.html:/app/index.html:ro
```

The template must keep the `__DATA__` placeholder, which the app replaces with the JSON payload.

### `DB_PATH`

Default: `/data/lightspeed.db`

The location of the SQLite database. Keep it under `/data` so it lives on the persistent volume.

## Build arguments

### `OOKLA_VERSION`

Default: `1.2.0`

The version of the Ookla Speedtest CLI downloaded at build time:

```bash
docker compose build --build-arg OOKLA_VERSION=1.2.0
```

## Storage

`compose.yaml` uses a named volume, `lightspeed-data`. The image creates `/data` owned by
uid 1000, and a new named volume inherits that ownership, so no `chown` is needed.

To use a bind mount instead, the host directory must be writable by uid 1000:

```bash
mkdir -p ./data && sudo chown 1000:1000 ./data
```

```yaml
    volumes:
      - ./data:/data
```

On SELinux hosts (RHEL, Fedora) with Podman or Docker, add `:Z` to the bind mount:
`./data:/data:Z`.
