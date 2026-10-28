# Configuration

Lightspeed Tracker is configured only through environment variables. With Docker Compose,
set them in the `environment:` section of `compose.yaml`, then run `docker compose up -d`
to apply them.

## Variables

### `DISPLAY_TZ`

Default: `Europe/Rome`

An IANA time zone name, such as `Europe/Rome` or `UTC`. It controls:

- the time labels on the 24h chart and in the "Last test" line
- where each day starts and ends for the daily summaries, and so for the 7-day and 30-day stats

Changing it later only affects new data. Days that were already summarised keep the
boundaries they were computed with.

### `RUN_MINUTE`

Default: `0`

The minute past each hour when the test runs. The schedule is computed in UTC, so DST
changes never skip or repeat a run. Picking a minute other than `0` (for example `7`)
avoids the busy top of the hour on Ookla's servers.

On startup, a test runs immediately if the last stored result is more than 55 minutes old.

### `SPEEDTEST_SERVER_ID`

Default: empty, so Ookla picks a server automatically.

Pinning a server keeps results comparable over time. To list nearby servers:

```bash
docker exec lightspeed-tracker speedtest -L
```

Then set, for example, `SPEEDTEST_SERVER_ID=4302`.

### `PORT`

Default: `8080`

The port the HTTP server listens on inside the container. To expose a different host port,
change the left side of the `ports:` mapping instead, for example `"9000:8080"`.

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
